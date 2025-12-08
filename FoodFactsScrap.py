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
