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

