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
    fruits_vegetables_nuts_percent: Optional[float] = None

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
    for h4 in soup.find_all("h4"):
        t = h4.get_text(" ", strip=True)
        if "Vegetarian status" in t:
            veg = _normalize_status(t.replace("Vegetarian status", ""))
        elif "Vegan status" in t:
            vegan = _normalize_status(t.replace("Vegan status", ""))
    return veg, vegan

