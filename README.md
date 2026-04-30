# Smart Food Guardian

## Overview

Smart Food Guardian is a multimodal AI system for classifying food products based on nutritional information, ingredients, and product images. The project uses machine learning models to predict nutriscore grades, nova groups, and other dietary labels by combining text data (ingredients, allergens), tabular nutritional data, and visual features from product images.

## Dataset

The primary dataset is `FoodFactsCleaned.csv`, derived from OpenFoodFacts data. It contains cleaned and preprocessed information about food products including:

- Product metadata (name, brand, barcode, etc.)
- Nutritional information per 100g
- Ingredients and allergens
- Geographical information
- Image paths
- Target labels: nutriscore_letter, nova_group, vegetarian_status, vegan_status, etc.

### Annotation Guidelines

#### Goal
Keep `FoodFactsCleaned.csv` consistent and model-ready by applying the same rules for:
- **Data normalization**
- **Label validity**
- **Missing values**
- **Derived fields integrity**

#### General rules (apply to all rows)
- **Do not invent values**: if the source is unknown/unavailable, leave the field empty (or keep the existing empty value).
- **Units**:
  - Nutrients ending with `_100g` are **grams per 100g** (except energy-related fields described below).
  - Ratios (e.g., `sugar_ratio`, `protein_ratio`) are dimensionless.
- **Numeric formatting**: store numbers as plain numeric values (no units, no % signs).
- **Text normalization**:
  - Use lowercase for cleaned fields (e.g., `brand_cleaned`, `ingredients_text_cleaned`).
  - Use `|` as a separator for multi-values in cleaned fields (e.g., `countries_cleaned`, `allergens_cleaned`).
- **Binary fields**: use `0/1` only.

#### Identity & traceability
- **`url`**: OpenFoodFacts product page URL.
- **`product_id`**: canonical identifier used to link product, images, and row.
- **`barcode`**: numeric barcode; if missing/invalid keep empty.
- **`product_name`, `brand`, `quantity`, `serving_size`**:
  - Keep as provided.
  - If multiple brands exist, keep raw in `brand` and normalized tokens in `brand_cleaned`.

#### Core labels (when annotating/classifying)
- **`nutriscore_letter`**:
  - Valid values: `a`, `b`, `c`, `d`, `e`.
  - If unavailable, set to `0` (as in the file) or empty, but keep it consistent across the dataset.
- **`nova_group`**:
  - Valid values: `1`, `2`, `3`, `4`.
  - Must be numeric.
- **Diet labels**:
  - **`vegetarian_status`** and **`vegan_status`**: use `1` for yes, `0` for no, empty if unknown.
- **Palm oil**:
  - **`contains_palm_oil`**: `1` if ingredients explicitly contain palm oil derivatives, else `0`, empty if unknown.

#### Ingredients, allergens, traces
- **`ingredients_text`**: raw ingredient string.
- **`ingredients_text_cleaned`**:
  - Lowercase.
  - Remove excessive punctuation and normalize whitespace.
  - Keep meaningful separators (commas) only if needed; otherwise tokens are fine.
- **`allergens` / `traces`**: raw strings.
- **`allergens_cleaned`**:
  - Lowercase.
  - Use `|`-separated canonical tokens (examples: `gluten`, `milk`, `eggs`, `fish`, `peanuts`, `tree_nuts`, `soybeans`, `sesame_seeds`, `sulphites`).
  - Do not add allergens that only appear in `traces` unless you are explicitly building a combined field.

#### Nutrition (per 100g)
These should be non-negative.
- **`fat_100g`, `saturated_fat_100g`, `carbohydrates_100g`, `sugars_100g`, `fiber_100g`, `proteins_100g`**:
  - Values are grams per 100g.
  - Ensure `saturated_fat_100g <= fat_100g` when both exist.
- **Nutrient level fields** (`nutrient_level_fat`, `nutrient_level_saturated_fat`, `nutrient_level_sugars`, `nutrient_level_salt`):
  - Keep numeric category codes as provided (do not remap unless the project defines a mapping).
- **Energy and salt logs**:
  - **`log_energy_kcal_100g`**: log-transformed energy in kcal/100g.
  - **`log_salt_100g`**: log-transformed salt in g/100g.
  - Do not compute logs for missing/zero values unless the pipeline defines the exact transform.

#### Sustainability
- **`ecoscore_grade`**: letter grade (as provided).
- **`ecoscore_score`**: numeric score.
- **`carbon_footprint_100g`**: numeric per 100g (keep units consistent with the source).

#### Derived features (keep consistent with the feature pipeline)
These columns are expected to be produced by the same preprocessing logic for all samples:
- **`additives_count`**: integer count of additives.
- **`additives` / `additives_cleaned`**:
  - Keep additive codes (e.g., `e300`) in cleaned form, separated by spaces.
- **`sugar_ratio`, `protein_ratio`**: ratios; must be between `0` and `1` when defined.
- **`energy_density`**: numeric (pipeline-defined).
- **`macro_balance`, `healthy_score`**: numeric (pipeline-defined); do not manually tweak.

#### Geography normalization
- **`countries`, `origins`, `manufacturing_places`**: raw.
- **`countries_cleaned`**:
  - Lowercase.
  - Use `|` separator for multiple countries (e.g., `france | germany | switzerland`).

#### Images
- **`main_image_url`**: source image URL.
- **`image_path`**, **`image_160_path`**: relative paths in the repo.
- **`has_image`**, **`has_image_160`**:
  - `1` if the corresponding file exists and is readable, else `0`.

#### Quality checks (recommended)
- **Row uniqueness**: `product_id` should be unique (or duplicates must be intentional).
- **Value ranges**:
  - Nutrients should be `>= 0`.
  - `sugar_ratio`/`protein_ratio` in `[0, 1]` when present.
- **Cross-field consistency**:
  - If `has_image_160 == 1`, `image_160_path` must be non-empty.
  - If `has_image == 1`, `image_path` must be non-empty.
- **Labels validity**:
  - `nova_group` in `{1,2,3,4}`.
  - `nutriscore_letter` in `{a,b,c,d,e}` (or `0`/empty if unknown, consistently).

## Project Structure

```
Smart-Food-Guardian/
├── FoodFactsCleaned.csv          # Main dataset
├── images_160/                   # Resized product images (160x160)
├── Preprocessing/                # Data preprocessing notebooks and scripts
│   ├── countinglabels.ipynb
│   ├── EDA.ipynb
│   ├── FoodFactsScrap.py
│   ├── imagepreprocessing.ipynb
│   ├── preprocessed_foodfacts_phase2.csv
│   ├── preprocessedPhase1FoodFacts.csv
│   ├── preprocessedPhase3FoodFacts.csv
│   ├── snacks_openfoodfacts.csv
│   ├── tabulardatapreprocessing.ipynb
│   ├── text_preprocessing.ipynb
│   └── product_images/
├── testing/                      # Baseline model evaluations
│   ├── image-only-baseline.ipynb
│   ├── tabular_only_baseline.ipynb
│   ├── text-only-model.ipynb
│   └── textTabular-model.ipynb
├── model1.ipynb                  # Multimodal: text + tabular + image (early fusion NN + XGBoost/SVM)
├── model2.ipynb                  # [Description needed]
├── model3.ipynb                  # [Description needed]
├── model4.ipynb                  # [Description needed]
├── model5.ipynb                  # [Description needed]
└── README.md
```

## Preprocessing

The preprocessing pipeline includes:

1. **Text Preprocessing** (`Preprocessing/text_preprocessing.ipynb`):
   - Cleaning and normalizing text fields (ingredients, allergens, brands, countries)
   - Tokenization and standardization

2. **Tabular Data Preprocessing** (`Preprocessing/tabularydatapreprocessing.ipynb`):
   - Handling missing values
   - Feature engineering (ratios, derived scores)
   - Normalization and scaling

3. **Image Preprocessing** (`Preprocessing/imagepreprocessing.ipynb`):
   - Downloading and resizing product images
   - Creating `images_160/` directory with 160x160 resized images

4. **EDA** (`Preprocessing/EDA.ipynb`):
   - Exploratory data analysis
   - Label distribution analysis

## Models

### Model 1: Multimodal Early Fusion (`model1.ipynb`)
- **Architecture**: Early fusion of text and tabular data through neural network, combined with image features
- **Text Processing**: Tokenization and embedding
- **Image Processing**: MobileNetV2 feature extraction
- **Fusion**: Feature-level fusion with XGBoost and SVM classifiers
- **Target**: Nutriscore classification

### Model 2 (`model2.ipynb`)
[Add description]

### Model 3 (`model3.ipynb`)
[Add description]

### Model 4 (`model4.ipynb`)
[Add description]

### Model 5 (`model5.ipynb`)
[Add description]

### Baseline Models (`testing/`)
- **Image-only**: CNN-based classification using product images
- **Tabular-only**: Traditional ML models on nutritional features
- **Text-only**: NLP models on ingredients and text data
- **Text+Tabular**: Combined text and tabular features

## Installation and Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd Smart-Food-Guardian
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Download the dataset and images (if not included):
   - Ensure `FoodFactsCleaned.csv` is in the root directory
   - Run image preprocessing if needed

## Usage

1. Run preprocessing notebooks in order:
   - `Preprocessing/EDA.ipynb`
   - `Preprocessing/text_preprocessing.ipynb`
   - `Preprocessing/tabularydatapreprocessing.ipynb`
   - `Preprocessing/imagepreprocessing.ipynb`

2. Execute model notebooks:
   - Start with baseline models in `testing/`
   - Run main models `model1.ipynb` through `model5.ipynb`

## Evaluation Metrics

- Accuracy
- F1-score (weighted)
- Classification report for each target label

## Contributing

[Add contribution guidelines]

## License

[Add license information]