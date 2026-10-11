# 🌫️ Explainable Street-Level AQI — Delhi

> **Environmental Hacks (DTU) · Air track · AWS-first · No hardware**

A web app where a user **clicks any point on a Delhi map** and instantly gets:
- Estimated PM2.5 in µg/m³ with a CPCB health category
- Confidence level based on distance to the nearest sensor
- **Top 3 SHAP-derived reasons** for the reading in plain English and Hindi
- One-sentence actionable health advice
- Plain-language audio explanations via voice playback

All inference runs entirely on AWS — no external AI APIs, no client-side ML.

**Live demo:** `https://aqi-frontend-991166714312.s3.ap-south-1.amazonaws.com/index.html`  
**API endpoint:** `https://6diafyett2.execute-api.ap-south-1.amazonaws.com/dev`

---

## What is built

| Feature | Status | Tier | Notes |
|---|---|---|---|
| Click-to-estimate PM2.5 with confidence and drivers | ✅ Live | 1 | Real-time ML inference & CPCB categories |
| XGBoost model trained on real PM2.5 readings | ✅ Live | 1 | Trained on station data + weather features |
| Delhi NCT-exclusive map bounding | ✅ Live | 1 | Locked to Delhi (`minZoom 10.2`, pan-bounds, boundary outline) |
| Interactive Delhi place search & autocomplete | ✅ Live | 1 | 30+ Delhi landmarks, metro hubs & localities |
| Quick Delhi hotspot chips | ✅ Live | 1 | 1-click estimates for CP, India Gate, Dwarka, Rohini, etc. |
| SHAP explainability — top 3 drivers per estimate | ✅ Live | 2 | Relative contribution bars & plain-language notes |
| Bedrock Claude 3 Haiku explanation + template fallback | ✅ Live | 2 | Plain-language "associated with" reasoning |
| "How accurate is this?" modal — RMSE chart, feature importance | ✅ Live | 2 | Leave-one-station-out CV & baseline comparison |
| Architecture diagram | ✅ Below | 3 | Full AWS serverless architecture documented |
| Bilingual EN & हिं support (interface & explanations) | ✅ Live | 4 | Dynamic language switcher with Hindi translations |
| Text-to-speech audio explanation | ✅ Live | 4 | In-browser synthesis + Polly audio fallback |
| Resident sign-in, alerts & saved places | ✅ Live | 8 | Saved locations & high AQI threshold notifications |
| Delhi Regional Zone selector | ✅ Live | 10 | Central, South, North, East, West Delhi & IGI Airport |
| 48-hour XGBoost forecast | ✅ Live | 5 | Multi-step temporal prediction with diurnal curve & confidence intervals |
| City-wide PM2.5 heatmap grid | ✅ Live | 6 | Spatial grid interpolation layer across Delhi NCT |
| Lowest-exposure route (Amazon Location Service) | ✅ Live | 7 | Clean-air walking, cycling & driving route comparisons |

---

## Interactive Map & UI Controls

- **Delhi-Only Map Bounding**: The map is restricted strictly to the National Capital Territory of Delhi (`[76.70, 28.25]` to `[77.48, 28.98]`). Users cannot pan away or zoom out (`minZoom: 10.2`) to view the entire country or globe. A highlighted Delhi NCT boundary overlay clearly frames the service zone.
- **48-Hour XGBoost Forecast (Tier 5)**: Dedicated side panel tab providing multi-step hourly projections over a 48-hour forward horizon for any selected Delhi point. Includes an interactive SVG chart with expanding 90% confidence bands, CPCB reference thresholds, summary cards for Peak PM2.5, Cleanest Window, and 48-Hour Average, and interactive hourly breakdowns driven by Delhi's diurnal boundary layer dynamics.
- **City-Wide PM2.5 Heatmap Grid (Tier 6)**: Spatial grid layer covering Delhi NCT with Inverse Distance Weighting (IDW) interpolation from real monitoring stations. Visualizes CPCB category color-coded cells and allows clicking any sector to trigger immediate street-level estimation. Toggleable via the "Area Heatmap Grid" button.
- **Clean Route Planner (Tier 7)**: Commute exposure optimizer comparing direct arterial routes vs green corridor routes for Walking, Cycling, and Driving modes across Delhi hubs. Quantifies duration, distance, and inhaled fine particulate reduction (typically 25%–38% savings) with dual route overlays rendered on the map.
- **Place Search & Autocomplete**: Real-time search across 30+ Delhi neighborhoods (e.g. Connaught Place, India Gate, Chandni Chowk, Hauz Khas, Saket, Dwarka, Rohini, Anand Vihar, IGI Airport). Pressing Enter or clicking a match flies the camera and estimates AQI on the spot.
- **Quick Hotspot Chips**: Prominent one-click shortcut buttons for Delhi's major hubs and traffic corridors.
- **Zone Selector**: Header dropdown to quickly pivot between Central, South, North, East, West Delhi, and IGI Airport zones.
- **Time Navigation**: Step backward hour-by-hour (up to 48 hours back) or tap "Now" to view current estimates.
- **Bilingual Interface (EN / हिं)**: Instant language toggle with localized headings, metrics, category chips, and translated advice.
- **Voice Playback ("Listen")**: Accessible audio button providing spoken explanations and health advice in Hindi or English.
- **Resident Profile & Alerts**: Modal for residents to save frequent locations (Home, Work, School) and configure alerts when AQI reaches Poor, Very Poor, or Severe.
- **Accuracy & Evaluation**: Interactive modal presenting XGBoost RMSE (18.4 µg/m³) vs persistence baseline (27.6 µg/m³), MAE, and top predictive features.

---

## Data sources & credits

| Source | What we use | Licence |
|---|---|---|
| [OpenAQ](https://openaq.org) | PM2.5 readings, Delhi CPCB stations | CC BY 4.0, original data from CPCB India |
| [Open-Meteo](https://open-meteo.com) | Hourly weather — temp, humidity, wind, BLH | Open-Meteo free tier, ERA5/ECMWF |
| [OpenStreetMap / Overpass](https://openstreetmap.org) | Road density within 1 km radius & basemap tiles | © OSM contributors, ODbL |
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov) | Active fire counts (Tier 6) | NASA FIRMS, MODIS/VIIRS |
| [MapLibre GL JS](https://maplibre.org) | Map rendering in browser | BSD-2-Clause |
| [Amazon Bedrock](https://aws.amazon.com/bedrock/) | Claude 3 Haiku explanation generation | AWS Commercial |

No proprietary datasets. No sensitive credentials are committed to this repository.

---

## Architecture (ap-south-1 · Mumbai)

```
┌─────────────────────────────────────────────────────────────┐
│                          BROWSER                            │
│  MapLibre GL JS (Delhi-bounded) ──► /estimate & /stations  │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTPS
                   ┌───────────▼───────────┐
                   │ API Gateway (dev)     │
                   └───────┬─────────┬─────┘
                           │         │
              ┌────────────▼──┐   ┌──▼────────────┐
              │ Lambda        │   │ Lambda        │
              │ aqi-estimate  │   │ aqi-stations  │
              └──┬────────────┘   └──┬────────────┘
                 │                   │
  ┌──────────────▼─┐                 │ S3 Station Cache / OpenAQ
  │ DynamoDB       │                 ▼
  │ aqi-cache(TTL) │        ┌─────────────────────────┐
  └────────────────┘        │ S3 aqi-models-*         │
                            │  nowcast_model.ubj      │
                            │  eval_results.json      │
                            │  feature_importance.json│
                            └────────┬────────────────┘
                                     │ (warm lambda cache)
                            ┌────────▼────────────┐
                            │ XGBoost + SHAP      │
                            └────────┬────────────┘
                                     │
                            ┌────────▼────────────┐
                            │ Bedrock Claude 3    │
                            │ (fallback: template)│
                            └─────────────────────┘

DATA PIPELINE (offline → S3):
  pull_openaq.py ──► aqi-raw-*/
  build_features.py ──► features_train.parquet ──► aqi-features-*/
  train_nowcast.py ──► nowcast_model.ubj + eval JSON ──► aqi-models-*/
```

---

## Model evaluation

| Metric | Value | Notes |
|---|---|---|
| Method | Leave-one-station-out CV & Time-split | Evaluated across 15 monitoring stations |
| Data window | Sept–Oct 2026 | 15 CPCB Delhi monitoring stations |
| **Model RMSE** | **18.4 µg/m³** | XGBoost on weather + road density + neighbor signals |
| Persistence baseline RMSE | 27.6 µg/m³ | 33% reduction in prediction error |
| **Model MAE** | **14.1 µg/m³** | Mean absolute error |
| Top features | Nearby station average (36%), Wind speed (22%), Road density (15%) | Local dispersion & traffic density |

> Our model uses weather, geography, and surrounding station readings, enabling street-level spatial interpolation to any Delhi point — which single-station persistence cannot do.

---

## AWS services used

| Service | Role |
|---|---|
| **Amazon S3** | Raw data, Parquet features, model artifacts, static frontend hosting |
| **AWS Lambda** | `/estimate` and `/stations` serverless inference |
| **Amazon API Gateway** | REST API with rate-limiting, throttling, and CORS |
| **Amazon DynamoDB** | 1-hour TTL cache for estimate responses |
| **Amazon Bedrock** | Claude 3 Haiku — plain-language AQI explanation |
| **Amazon Location Service / OSM** | Map rendering & Delhi spatial boundaries |
| **AWS IAM** | Least-privilege roles per Lambda execution |
| **Amazon CloudWatch** | Error-rate and latency monitoring |
| **AWS SAM / CloudFormation** | Infrastructure as Code |

---

## How to run

### Prerequisites
- AWS CLI v2 with configured profile (`ap-south-1`)
- AWS SAM CLI
- Python 3.12+

### Running the Frontend Locally

```bash
# Serve static frontend locally
python3 -m http.server 8080 --directory frontend/src
# Open http://localhost:8080/index.html in your browser
```

### Backend deploy (AWS SAM)

```bash
cd infra
sam build --template-file template.yaml
sam deploy
```

The API Gateway URL is printed as `ApiUrl` in the stack outputs.

### Frontend S3 Deploy

Upload the web application bundle to S3:
```bash
aws s3 sync frontend/src/ s3://aqi-frontend-991166714312/ --profile "Shourya Sankrit"
```

### Data pipeline

```bash
# Set keys in environment first
export OPENAQ_API_KEY="your-key"
export FIRMS_MAP_KEY="your-key"

cd backend/data_pipeline
pip install -r requirements-pipeline.txt
python pull_openaq.py --months 6 --city delhi
python build_features.py --city delhi --upload
```

### Model training

```bash
cd backend/ml
pip install -r requirements-ml.txt
python train_nowcast.py --upload
```

---

## Limits (honest)

- Estimates are from a model trained on government monitoring-station data. They are **model estimates, not calibrated physical sensor measurements**.
- Delhi has a finite number of CPCB monitoring stations. Accuracy decreases at points far from any station.
- The data window is bounded by OpenAQ archive availability and the pull date.
- SHAP values describe feature contributions to the model prediction, not absolute verified physical causation.

---

## No keys in this repo

All API keys and cloud credentials are stored in AWS Secrets Manager or Lambda environment variables only. The frontend makes no direct calls to private third-party APIs.
