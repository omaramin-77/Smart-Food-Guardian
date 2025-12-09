import csv
import json
import os
import re
import time
import argparse
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


# Base configuration
BASE_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
BASE_PRODUCT_URL = "https://world.openfoodfacts.org/product/"
DEFAULT_QUERY = "Snacks"
DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 10
USER_AGENT = "SmartFoodGuardian-ML-Project/0.1 (https://openfoodfacts.org)"


session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


@dataclass
class ProductRecord:
    url: str
    product_name: Optional[str] = None
    barcode: Optional[str] = None
    brand: Optional[str] = None
    quantity: Optional[str] = None
    serving_size: Optional[str] = None

    nutriscore_letter: Optional[str] = None
    nova_group: Optional[int] = None

    ingredients_text: Optional[str] = None
    allergens: Optional[str] = None
    traces: Optional[str] = None

    energy_kj_100g: Optional[float] = None
    energy_kcal_100g: Optional[float] = None
    fat_100g: Optional[float] = None
    saturated_fat_100g: Optional[float] = None
    carbohydrates_100g: Optional[float] = None
    sugars_100g: Optional[float] = None
    fiber_100g: Optional[float] = None
    proteins_100g: Optional[float] = None
    salt_100g: Optional[float] = None

    main_image_url: Optional[str] = None
    categories: Optional[str] = None

    contains_palm_oil: Optional[bool] = None
    vegetarian_status: Optional[str] = None
    vegan_status: Optional[str] = None

    nutrient_level_fat: Optional[str] = None
    nutrient_level_saturated_fat: Optional[str] = None
    nutrient_level_sugars: Optional[str] = None
    nutrient_level_salt: Optional[str] = None

    additives: List[str] = field(default_factory=list)

    packaging: Optional[str] = None
    stores: Optional[str] = None
    countries: Optional[str] = None
    origins: Optional[str] = None
    manufacturing_places: Optional[str] = None

    ecoscore_grade: Optional[str] = None
    ecoscore_score: Optional[float] = None
    carbon_footprint_100g: Optional[float] = None

def _fetch_json_search_page(page: int, query: str = DEFAULT_QUERY, page_size: int = DEFAULT_PAGE_SIZE) -> List[str]:
    """Return list of product page URLs from a search page using the JSON API.

    This uses the same endpoint as the HTML search page but with json=1.
    """

    params = {
        "action": "process",
        "search_terms": query,
        "sort_by": "unique_scans_n",
        "page_size": page_size,
        "page": page,
        "json": 1,
    }
    resp = session.get(BASE_SEARCH_URL, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    urls: List[str] = []

    for p in data.get("products", []):
        url = p.get("url")
        code = p.get("code")
        if not url and code:
            url = f"{BASE_PRODUCT_URL}{code}"
        if url:
            urls.append(url)

    return urls

FACET_SNACKS_URL_TEMPLATE = "https://world.openfoodfacts.org/facets/categories/snacks/{page}?sort_by=nutriscore_score"


def _fetch_facet_snacks_page(page: int) -> List[str]:
    url = FACET_SNACKS_URL_TEMPLATE.format(page=page)
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    html = resp.text

    seen: set[str] = set()
    urls: List[str] = []

    for m in re.finditer(
        r'"url"\s*:\s*"(https://world\.openfoodfacts\.org/product/[^"\\]+)"',
        html,
    ):
        u = m.group(1)
        if u not in seen:
            seen.add(u)
            urls.append(u)

    if urls:
        return urls

    soup = BeautifulSoup(html, "html.parser")
    for a in soup.select("a[href*='/product/']"):
        href = a.get("href")
        if not href:
            continue
        if href.startswith("//"):
            full_url = "https:" + href
        elif href.startswith("/"):
            full_url = "https://world.openfoodfacts.org" + href
        else:
            full_url = href
        if full_url not in seen and "/product/" in full_url:
            seen.add(full_url)
            urls.append(full_url)

    return urls


def _get_soup(url: str) -> BeautifulSoup:
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")

def _get_text_or_none(soup: BeautifulSoup, selector: str) -> Optional[str]:
    el = soup.select_one(selector)
    if not el:
        return None
    text = el.get_text(" ", strip=True)
    return text or None


def _parse_float(text: str) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"([-+]?[0-9]+(?:[.,][0-9]+)?)", text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None

def _parse_energy(text: str) -> (Optional[float], Optional[float]):
    """Parse energy string like '2,380 kj (571 kcal)' into kJ and kcal."""

    if not text:
        return None, None
    kj = None
    kcal = None

    m_kj = re.search(r"([0-9][0-9.,]*)\s*k[jJ]", text)
    if m_kj:
        kj = _parse_float(m_kj.group(1))

    m_kcal = re.search(r"([0-9][0-9.,]*)\s*kcal", text, flags=re.I)
    if m_kcal:
        kcal = _parse_float(m_kcal.group(1))

    return kj, kcal


def _parse_product_name(soup: BeautifulSoup) -> Optional[str]:
    h1 = soup.select_one("h1[itemprop='name']") or soup.find("h1")
    return h1.get_text(" ", strip=True) if h1 else None


def _parse_barcode(soup: BeautifulSoup) -> Optional[str]:
    span = soup.select_one("#barcode") or soup.select_one("span[itemprop='gtin13']")
    return span.get_text(strip=True) if span else None

def _parse_field_span(soup: BeautifulSoup, field_id: str) -> Optional[str]:
    return _get_text_or_none(soup, f"#{field_id}_value")

def _parse_ingredients_block(soup: BeautifulSoup) -> (Optional[str], Optional[str], Optional[str]):
    """Return (ingredients_text, allergens, traces)."""

    panel = soup.select_one("#panel_ingredients_content")
    if not panel:
        return None, None, None

    panel_texts = panel.select(".panel_text")
    ingredients_text = None
    allergens = None
    traces = None

    if panel_texts:
        ingredients_text = panel_texts[0].get_text(" ", strip=True) or None

    for div in panel_texts[1:]:
        text = div.get_text(" ", strip=True)
        if text.startswith("Allergens:"):
            allergens = text.replace("Allergens:", "", 1).strip() or None
        elif text.startswith("Traces:"):
            traces = text.replace("Traces:", "", 1).strip() or None

    return ingredients_text, allergens, traces

def _parse_nutrition_table(soup: BeautifulSoup, record: ProductRecord) -> None:
    table = soup.find("table", attrs={"aria-label": "Nutrition facts"})
    if not table:
        return

    tbody = table.find("tbody") or table
    for row in tbody.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 2:
            continue
        label = cols[0].get_text(" ", strip=True).lower()
        value_100g = cols[1].get_text(" ", strip=True)

        if "energy" in label:
            kj, kcal = _parse_energy(value_100g)
            record.energy_kj_100g = kj
            record.energy_kcal_100g = kcal
        elif label == "fat":
            record.fat_100g = _parse_float(value_100g)
        elif "saturated fat" in label:
            record.saturated_fat_100g = _parse_float(value_100g)
        elif label == "carbohydrates":
            record.carbohydrates_100g = _parse_float(value_100g)
        elif "sugars" in label:
            record.sugars_100g = _parse_float(value_100g)
        elif "fiber" in label:
            record.fiber_100g = _parse_float(value_100g)
        elif "proteins" in label or label == "protein":
            record.proteins_100g = _parse_float(value_100g)
        elif "salt" in label:
            record.salt_100g = _parse_float(value_100g)


def _parse_serving_size(soup: BeautifulSoup) -> Optional[str]:
    for strong in soup.find_all("strong"):
        txt = strong.get_text(strip=True)
        if txt.startswith("Serving size"):
            parent_text = strong.parent.get_text(" ", strip=True)
            cleaned = re.sub(r"^Serving size:\s*", "", parent_text).strip()
            return cleaned or None
    return None


def _parse_nutriscore_letter(soup: BeautifulSoup) -> Optional[str]:
    candidates = []
    for h4 in soup.find_all("h4"):
        t = h4.get_text(" ", strip=True)
        if "Nutri-Score" in t:
            candidates.append(t)
    if not candidates:
        for p in soup.find_all("p"):
            t = p.get_text(" ", strip=True)
            if "Nutri-Score" in t:
                candidates.append(t)
    for t in candidates:
        m = re.search(r"Nutri-Score[^A-E]*([A-E])", t)
        if m:
            return m.group(1)
    return None


def _parse_nova_group(soup: BeautifulSoup) -> Optional[int]:
    for p in soup.find_all("p"):
        t = p.get_text(" ", strip=True)
        m = re.search(r"product is in the\s+(\d)\s*-", t)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    for h4 in soup.find_all("h4"):
        t = h4.get_text(" ", strip=True)
        m = re.search(r"nova\s*group\s*(\d)", t, flags=re.I)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    return None


def _parse_main_image_url(soup: BeautifulSoup) -> Optional[str]:
    metas = soup.find_all("meta", attrs={"property": "og:image"})
    for meta in metas:
        url = meta.get("content")
        if url and "/images/products/" in url:
            return url
    if metas:
        url = metas[-1].get("content")
        if url:
            return url
    img = soup.select_one("img.product_image")
    if img and img.get("src"):
        src = img["src"]
        if src.startswith("//"):
            return "https:" + src
        if src.startswith("/"):
            return "https://world.openfoodfacts.org" + src
        return src
    return None


def _parse_categories(soup: BeautifulSoup) -> Optional[str]:
    container = soup.select_one("#field_categories_value")
    if not container:
        return None
    names: List[str] = []
    for a in container.find_all("a"):
        txt = a.get_text(" ", strip=True)
        if txt:
            names.append(txt)
    if not names:
        raw = container.get_text(" ", strip=True)
        return raw or None
    return ", ".join(names)


def _parse_palm_oil_flag(soup: BeautifulSoup) -> Optional[bool]:
    texts = soup.select(".panel_text")
    for div in texts:
        t = div.get_text(" ", strip=True).lower()
        if "ingredients that contain palm oil" in t:
            return True
    return None

def _normalize_status(text: str) -> str:
    t = text.strip().lower()
    if "unknown" in t:
        return "unknown"
    if "non-vegetarian" in t or "not vegetarian" in t:
        return "no"
    if "non-vegan" in t or "not vegan" in t:
        return "no"
    if "vegetarian" in t or "vegan" in t:
        return "yes"
    return text.strip()


def _parse_veg_flags(soup: BeautifulSoup) -> (Optional[str], Optional[str]):
    veg = None
    vegan = None

    vegan_panel = soup.select_one("#panel_ingredients_analysis_en-vegan h4")
    if vegan_panel:
        vegan = _normalize_status(vegan_panel.get_text(" ", strip=True))

    vegetarian_panel = soup.select_one("#panel_ingredients_analysis_en-vegetarian h4")
    if vegetarian_panel:
        veg = _normalize_status(vegetarian_panel.get_text(" ", strip=True))

    if veg is None or vegan is None:
        for h4 in soup.find_all("h4"):
            t = h4.get_text(" ", strip=True)
            if "Vegetarian status" in t and veg is None:
                veg = _normalize_status(t.replace("Vegetarian status", ""))
            elif "Vegan status" in t and vegan is None:
                vegan = _normalize_status(t.replace("Vegan status", ""))

    if veg is None or vegan is None:
        ordered = soup.select_one("#ordered_ingredients_list")
        if ordered:
            text = ordered.get_text(" ", strip=True).lower()
            if vegan is None:
                m = re.search(r"vegan:\s*(yes|no|unknown)", text)
                if m:
                    vegan = _normalize_status(m.group(0))
            if veg is None:
                m = re.search(r"vegetarian:\s*(yes|no|unknown)", text)
                if m:
                    veg = _normalize_status(m.group(0))

    return veg, vegan


def _parse_nutrient_levels(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
    result: Dict[str, Optional[str]] = {
        "fat": None,
        "saturated_fat": None,
        "sugars": None,
        "salt": None,
    }

    panel = soup.select_one("#panel_nutrient_levels_content")
    if not panel:
        return result

    for li in panel.select("li.accordion-navigation"):
        h4 = li.find("h4")
        if not h4:
            continue
        text = h4.get_text(" ", strip=True).lower()
        if text.startswith("fat "):
            if "high" in text:
                result["fat"] = "high"
            elif "moderate" in text:
                result["fat"] = "moderate"
            elif "low" in text:
                result["fat"] = "low"
        elif text.startswith("saturated fat"):
            if "high" in text:
                result["saturated_fat"] = "high"
            elif "moderate" in text:
                result["saturated_fat"] = "moderate"
            elif "low" in text:
                result["saturated_fat"] = "low"
        elif text.startswith("sugars"):
            if "high" in text:
                result["sugars"] = "high"
            elif "moderate" in text:
                result["sugars"] = "moderate"
            elif "low" in text:
                result["sugars"] = "low"
        elif text.startswith("salt"):
            if "high" in text:
                result["salt"] = "high"
            elif "moderate" in text:
                result["salt"] = "moderate"
            elif "low" in text:
                result["salt"] = "low"

    return result


def _parse_additives(soup: BeautifulSoup) -> List[str]:
    panel = soup.select_one("#panel_additives_content")
    if not panel:
        return []
    names: List[str] = []
    for h4 in panel.find_all("h4"):
        t = h4.get_text(" ", strip=True)
        if t:
            names.append(t)
    return names


def _parse_ecoscore_and_carbon(soup: BeautifulSoup) -> (Optional[str], Optional[float], Optional[float]):
    ecoscore_grade = None
    ecoscore_score = None
    carbon = None

    panel_total = soup.select_one("#panel_environmental_score_total")
    if panel_total:
        h4 = panel_total.find("h4")
        if h4:
            t = h4.get_text(" ", strip=True)
            m = re.search(
                r"Impact for this product:\s*([A-E])\s*\(Score:\s*([0-9]+(?:[.,][0-9]+)?)/100\)",
                t,
                flags=re.I,
            )
            if m:
                ecoscore_grade = m.group(1).upper()
                ecoscore_score = _parse_float(m.group(2))
            else:
                m_letter = re.search(r"([A-E])", t, flags=re.I)
                if m_letter and ecoscore_grade is None:
                    ecoscore_grade = m_letter.group(1).upper()
                m_score = re.search(r"([0-9]+(?:[.,][0-9]+)?)/100", t)
                if m_score and ecoscore_score is None:
                    ecoscore_score = _parse_float(m_score.group(1))

        if ecoscore_score is None:
            for div in panel_total.select(".panel_text"):
                text = div.get_text(" ", strip=True)
                m = re.search(r"Final score:\s*([0-9]+(?:[.,][0-9]+)?)/100", text, flags=re.I)
                if m:
                    ecoscore_score = _parse_float(m.group(1))
                    break

    if ecoscore_grade is None:
        for h4 in soup.find_all("h4"):
            t = h4.get_text(" ", strip=True)
            if "Eco-Score" in t or "Ecoscore" in t:
                m = re.search(r"Eco-Score\s*([A-E])", t, flags=re.I)
                if m:
                    ecoscore_grade = m.group(1).upper()
                    break

    panel_carbon = soup.select_one("#panel_carbon_footprint")
    if panel_carbon:
        text = panel_carbon.get_text(" ", strip=True)
        m = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*g\b", text)
        if m:
            carbon = _parse_float(m.group(1))

    if carbon is None:
        for p in soup.find_all("p"):
            t = p.get_text(" ", strip=True)
            if "carbon footprint" in t.lower():
                m = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*(?:kg|g)\b", t, flags=re.I)
                if m:
                    carbon = _parse_float(m.group(1))
                    break

    return ecoscore_grade, ecoscore_score, carbon


def _download_image(url: str, dest_dir: str, base_name: str) -> Optional[str]:
    os.makedirs(dest_dir, exist_ok=True)

    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[1] or ".jpg"
    safe_base = re.sub(r"[^A-Za-z0-9_.-]+", "_", base_name or "image")
    dest_path = os.path.join(dest_dir, safe_base + ext)

    if os.path.exists(dest_path):
        return dest_path

    try:
        resp = session.get(url, stream=True, timeout=30)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return dest_path
    except Exception:
        return None


def scrape_product(url: str, download_images: bool = False, images_dir: str = "product_images") -> ProductRecord:
    soup = _get_soup(url)

    record = ProductRecord(url=url)

    record.product_name = _parse_product_name(soup)
    record.barcode = _parse_barcode(soup)

    record.brand = _parse_field_span(soup, "field_brands")
    record.quantity = _parse_field_span(soup, "field_quantity")
    record.packaging = _parse_field_span(soup, "field_packaging")
    record.stores = _parse_field_span(soup, "field_stores")
    record.countries = _parse_field_span(soup, "field_countries")
    record.origins = _parse_field_span(soup, "field_origins")
    record.manufacturing_places = _parse_field_span(soup, "field_manufacturing_places")

    record.serving_size = _parse_serving_size(soup)

    ingredients_text, allergens, traces = _parse_ingredients_block(soup)
    record.ingredients_text = ingredients_text
    record.allergens = allergens
    record.traces = traces

    _parse_nutrition_table(soup, record)

    record.nutriscore_letter = _parse_nutriscore_letter(soup)
    record.nova_group = _parse_nova_group(soup)

    record.main_image_url = _parse_main_image_url(soup)
    record.categories = _parse_categories(soup)

    record.contains_palm_oil = _parse_palm_oil_flag(soup)
    veg, vegan = _parse_veg_flags(soup)
    record.vegetarian_status = veg
    record.vegan_status = vegan

    nutrient_levels = _parse_nutrient_levels(soup)
    record.nutrient_level_fat = nutrient_levels.get("fat")
    record.nutrient_level_saturated_fat = nutrient_levels.get("saturated_fat")
    record.nutrient_level_sugars = nutrient_levels.get("sugars")
    record.nutrient_level_salt = nutrient_levels.get("salt")

    record.additives = _parse_additives(soup)

    ecoscore_grade, carbon = _parse_ecoscore_and_carbon(soup)
    record.ecoscore_grade = ecoscore_grade
    record.carbon_footprint_100g = carbon

    if download_images and record.main_image_url:
        base_name = record.barcode or (record.product_name or "image").replace(" ", "_")
        _download_image(record.main_image_url, images_dir, base_name)

    return record


def scrape_snacks_dataset(
    max_pages: int = DEFAULT_MAX_PAGES,
    page_size: int = DEFAULT_PAGE_SIZE,
    query: str = DEFAULT_QUERY,
    delay_between_requests: float = 0.5,
    download_images: bool = False,
    images_dir: str = "product_images",
    start_page: int = 1,
    pages_to_scrape: Optional[int] = None,
) -> List[ProductRecord]:
    products: List[ProductRecord] = []
    seen_urls: set[str] = set()

    if pages_to_scrape is not None:
        end_page = max(start_page, start_page + pages_to_scrape - 1)
        page_iter = range(start_page, end_page + 1)
    else:
        page_iter = range(1, max_pages + 1)

    for page in page_iter:
        print(f"[Search] Page {page}...")
        try:
            urls = _fetch_json_search_page(page, query=query, page_size=page_size)
        except Exception as e:
            print(f"  !! Failed to fetch search page {page}: {e}")
            break

        if not urls:
            print("  No more products found, stopping.")
            break

        for url in urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)

            print(f"  [Product] {url}")
            try:
                record = scrape_product(url, download_images=download_images, images_dir=images_dir)
                products.append(record)
            except Exception as e:
                print(f"    !! Failed to scrape product {url}: {e}")

            if delay_between_requests > 0:
                time.sleep(delay_between_requests)

    return products


def save_to_json(records: List[ProductRecord], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in records], f, ensure_ascii=False, indent=2)
    print(f"Saved JSON to {path} ({len(records)} products)")


def save_to_csv(records: List[ProductRecord], path: str, append: bool = True) -> None:
    if not records:
        print("No records to save to CSV.")
        return

    fieldnames = list(asdict(records[0]).keys())
    file_exists = os.path.exists(path)
    mode = "a" if append and file_exists else "w"
    with open(path, mode, encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not append or not file_exists:
            writer.writeheader()
        for r in records:
            writer.writerow(asdict(r))
    print(f"Saved CSV to {path} ({len(records)} products)")


def main() -> None:
    # You can adjust these defaults or wire this up to argparse later.
    page_size = DEFAULT_PAGE_SIZE
    download_images = True

    parser = argparse.ArgumentParser()
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--append-csv", action="store_true")
    args = parser.parse_args()

    records = scrape_snacks_dataset(
        page_size=page_size,
        query=DEFAULT_QUERY,
        delay_between_requests=0.5,
        download_images=download_images,
        images_dir="product_images",
        start_page=args.start_page,
        pages_to_scrape=args.pages,
    )

    save_to_json(records, "snacks_openfoodfacts.json")
    save_to_csv(records, "snacks_openfoodfacts.csv", append=args.append_csv)


if __name__ == "__main__":
    main()
