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
