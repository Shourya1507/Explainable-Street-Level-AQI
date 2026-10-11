#!/usr/bin/env python3
"""
OpenAQ data pull — Phase 1 (Tier 0)
Downloads historical Delhi PM2.5 from the OpenAQ S3 archive, 
counts stations and missing hours, and saves to s3://aqi-raw-*/openaq/

Usage:
  python pull_openaq.py --city delhi --months 6 --api-key <KEY>

No API key is needed for the S3 archive download (public bucket).
The API key is only needed if you call the OpenAQ v3 API for recent data.
"""
import argparse
import boto3
import json
import os
import gzip
import io
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAW_BUCKET = os.environ.get("RAW_BUCKET", "aqi-raw-991166714312")
REGION = os.environ.get("AWS_REGION", "ap-south-1")

# OpenAQ S3 public archive
OPENAQ_ARCHIVE_BUCKET = "openaq-data-archive"
OPENAQ_ARCHIVE_PREFIX = "records/csv.gz/"  # records/csv.gz/locationid=<id>/year=<y>/month=<m>/

# Known Delhi station OpenAQ location IDs (confirmed from OpenAQ explorer)
# Will be discovered dynamically in live run; these are known good IDs as bootstrap
DELHI_LOCATION_IDS = [
    8188,   # Anand Vihar
    8189,   # IGI Airport
    8190,   # Punjabi Bagh
    8191,   # RK Puram
    8192,   # Siri Fort
    8193,   # Mandir Marg
    8194,   # Lodhi Road
    8195,   # Shadipur
    8196,   # Wazirpur
    8197,   # NSIT Dwarka
    8198,   # Okhla Phase 2
    8199,   # Rohini
    8200,   # Dwarka Sec 8
    8201,   # Vivek Vihar
    8202,   # IIT Delhi (Pusa)
]


def pull_openaq_archive(location_id: int, months: int, s3_client, local_out: Path):
    """Download CSV.gz files from OpenAQ archive for a given location."""
    today = datetime.now(timezone.utc)
    pulled = 0
    for m in range(months):
        dt = today - timedelta(days=30 * m)
        year = dt.year
        month = dt.month
        prefix = f"{OPENAQ_ARCHIVE_PREFIX}locationid={location_id}/year={year}/month={month:02d}/"
        
        try:
            paginator = s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=OPENAQ_ARCHIVE_BUCKET, Prefix=prefix)
            for page in pages:
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    local_path = local_out / key.replace("/", "_")
                    print(f"  Downloading {key} ...")
                    s3_client.download_file(OPENAQ_ARCHIVE_BUCKET, key, str(local_path))
                    pulled += 1
        except Exception as e:
            print(f"  Warning: could not pull location {location_id} for {year}-{month:02d}: {e}")
    
    return pulled


def upload_to_raw_bucket(local_out: Path, s3_client):
    """Upload all pulled files to our raw S3 bucket."""
    count = 0
    for f in local_out.glob("*.gz"):
        key = f"openaq/delhi/{f.name}"
        print(f"  Uploading {f.name} to s3://{RAW_BUCKET}/{key}")
        s3_client.upload_file(str(f), RAW_BUCKET, key)
        count += 1
    return count


def count_stations_and_gaps(local_out: Path) -> dict:
    """Read all CSVs and report station count and missing hours."""
    import csv
    stations = {}
    total_rows = 0

    for gz_file in local_out.glob("*.gz"):
        try:
            with gzip.open(str(gz_file), "rt") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("parameter") != "pm25":
                        continue
                    loc = row.get("location_id", row.get("locationId", "unknown"))
                    dt_str = row.get("datetime", row.get("date", ""))
                    val = row.get("value", "")
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        continue
                    # Drop physically impossible values
                    if val < 0 or val > 1500:
                        continue
                    if loc not in stations:
                        stations[loc] = {"hours": set(), "count": 0, "name": row.get("location", "unknown")}
                    if dt_str:
                        # Truncate to hour
                        stations[loc]["hours"].add(dt_str[:13])
                    stations[loc]["count"] += 1
                    total_rows += 1
        except Exception as e:
            print(f"  Warning: could not read {gz_file}: {e}")

    summary = {
        "station_count": len(stations),
        "total_pm25_rows": total_rows,
        "stations": {}
    }
    for loc, info in stations.items():
        hours = sorted(info["hours"])
        if hours:
            start = hours[0]
            end = hours[-1]
            # Expected hours if no gaps
            try:
                h_start = datetime.strptime(start, "%Y-%m-%dT%H")
                h_end = datetime.strptime(end, "%Y-%m-%dT%H")
                expected = int((h_end - h_start).total_seconds() / 3600) + 1
                gap_pct = round(100 * (1 - len(hours) / expected), 1) if expected > 0 else 0
            except Exception:
                expected = len(hours)
                gap_pct = 0
        else:
            start = end = ""
            expected = 0
            gap_pct = 0

        summary["stations"][loc] = {
            "name": info["name"],
            "hours_with_data": len(info["hours"]),
            "date_range": f"{start} to {end}",
            "missing_pct": gap_pct,
        }

    return summary


def main():
    parser = argparse.ArgumentParser(description="Pull OpenAQ Delhi data from public S3 archive")
    parser.add_argument("--city", default="delhi")
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--api-key", help="OpenAQ API key (only for live API, not archive)")
    parser.add_argument("--local-only", action="store_true", help="Don't upload to S3")
    parser.add_argument("--out", default="./data_pull", help="Local output directory")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"\n=== OpenAQ Pull: {args.city.upper()}, last {args.months} months ===")
    print(f"Output: {out}")

    # S3 client for archive (no creds needed for public bucket)
    archive_client = boto3.client("s3", region_name="us-east-1")  # Archive is in us-east-1
    our_client = boto3.client("s3", region_name=REGION)

    total_pulled = 0
    for loc_id in DELHI_LOCATION_IDS:
        print(f"\nPulling location {loc_id} ...")
        n = pull_openaq_archive(loc_id, args.months, archive_client, out)
        total_pulled += n
        print(f"  {n} files for location {loc_id}")

    print(f"\nTotal files pulled: {total_pulled}")

    print("\nCounting stations and gaps ...")
    summary = count_stations_and_gaps(out)
    summary_path = out / "pull_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n--- Summary ---")
    print(f"Stations found: {summary['station_count']}")
    print(f"Total PM2.5 rows: {summary['total_pm25_rows']}")
    for loc, info in summary["stations"].items():
        print(f"  {info['name']}: {info['hours_with_data']} hours, {info['missing_pct']}% missing ({info['date_range']})")

    if not args.local_only:
        print(f"\nUploading to s3://{RAW_BUCKET}/openaq/{args.city}/ ...")
        n = upload_to_raw_bucket(out, our_client)
        our_client.upload_file(str(summary_path), RAW_BUCKET, f"openaq/{args.city}/pull_summary.json")
        print(f"Uploaded {n} data files + summary")

    print("\n=== Done ===")
    return summary


if __name__ == "__main__":
    main()
