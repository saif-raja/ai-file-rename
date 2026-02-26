#!/usr/bin/env python3
"""
Generate comprehensive test fixture files for ai-file-rename tool.
Creates real files with actual content across many formats and edge cases.
"""

import os
import io
import struct
import wave
import zipfile
import sqlite3
import random

# Third-party
from PIL import Image
from fpdf import FPDF
from docx import Document as DocxDocument
from pptx import Presentation
from pptx.util import Inches
import openpyxl

BASE = "/Users/saifraja/Github/z misc/ai-file-rename/tests/fixtures/sample-files"


def ensure_dir(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def filepath(*parts):
    p = os.path.join(BASE, *parts)
    ensure_dir(p)
    return p


# ============================================================
# IMAGES
# ============================================================
def create_images():
    print("Creating images...")

    # IMG_20190412_143022.jpg - 10x10 solid orange JPEG
    img = Image.new("RGB", (10, 10), color=(255, 165, 0))
    img.save(filepath("images", "IMG_20190412_143022.jpg"), "JPEG")

    # Screenshot 2023-11-15 at 3.42.12 PM.png - 10x10 blue PNG
    img = Image.new("RGB", (10, 10), color=(30, 100, 220))
    img.save(filepath("images", "Screenshot 2023-11-15 at 3.42.12 PM.png"), "PNG")

    # a7f3b2c1d4e5.png - random hash name, 10x10 green PNG
    img = Image.new("RGB", (10, 10), color=(0, 200, 50))
    img.save(filepath("images", "a7f3b2c1d4e5.png"), "PNG")

    # photo.heic - HEIC placeholder (small binary with comment)
    p = filepath("images", "photo.heic")
    with open(p, "wb") as f:
        # Write a minimal ftyp box that mimics HEIC structure
        # ftyp box: size(4) + 'ftyp'(4) + brand(4) + version(4)
        ftyp = b'\x00\x00\x00\x18'  # size = 24
        ftyp += b'ftyp'
        ftyp += b'heic'  # major brand
        ftyp += b'\x00\x00\x00\x00'  # minor version
        ftyp += b'heic'  # compatible brand
        ftyp += b'mif1'  # compatible brand
        f.write(ftyp)
        # Pad with some data to make it non-trivial
        f.write(b'\x00' * 256)

    # image(1).bmp - 10x10 red BMP
    img = Image.new("RGB", (10, 10), color=(255, 0, 0))
    img.save(filepath("images", "image(1).bmp"), "BMP")

    # download.gif - 10x10 purple 1-frame GIF
    img = Image.new("RGB", (10, 10), color=(128, 0, 128))
    img.save(filepath("images", "download.gif"), "GIF")

    print("  images/ done")


# ============================================================
# DOCUMENTS
# ============================================================
def create_documents():
    print("Creating documents...")

    # document.pdf - "Quarterly Revenue Report Q3 2023"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 20, "Quarterly Revenue Report Q3 2023", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 12)
    pdf.ln(10)
    pdf.multi_cell(0, 8, (
        "Executive Summary\n\n"
        "This report summarizes the financial performance of Acme Corp during the third quarter of 2023. "
        "Total revenue reached $4.2M, representing a 15% increase over Q2. Key growth drivers included "
        "the launch of our SaaS platform and expansion into the European market.\n\n"
        "Revenue Breakdown:\n"
        "- Product Sales: $2.1M (+12% QoQ)\n"
        "- Service Revenue: $1.4M (+18% QoQ)\n"
        "- Licensing Fees: $700K (+22% QoQ)\n\n"
        "Net profit margin improved to 23.4%, up from 21.1% in Q2."
    ))
    pdf.output(filepath("documents", "document.pdf"))

    # document(1).pdf - "Annual Security Audit 2023"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 20, "Annual Security Audit 2023", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 12)
    pdf.ln(10)
    pdf.multi_cell(0, 8, (
        "Confidential - Internal Use Only\n\n"
        "This document presents the findings of the 2023 annual security audit conducted by "
        "CyberShield Consulting for TechVentures Inc.\n\n"
        "Key Findings:\n"
        "1. Critical: SQL injection vulnerability in user authentication module\n"
        "2. High: Outdated TLS 1.1 still enabled on 3 production servers\n"
        "3. Medium: Insufficient logging in payment processing pipeline\n"
        "4. Low: Default admin credentials on staging environment\n\n"
        "Remediation Timeline:\n"
        "- Critical issues: 7 days\n"
        "- High issues: 30 days\n"
        "- Medium issues: 60 days\n"
        "- Low issues: 90 days"
    ))
    pdf.output(filepath("documents", "document(1).pdf"))

    # presentation_final_v2_FINAL.pptx
    prs = Presentation()
    slide_layout = prs.slide_layouts[0]  # Title slide
    slide = prs.slides.add_slide(slide_layout)
    title = slide.shapes.title
    subtitle = slide.placeholders[1]
    title.text = "Q4 Product Strategy"
    subtitle.text = "Final Version - Board Presentation\nDecember 2023"

    slide_layout = prs.slide_layouts[1]  # Title and Content
    slide = prs.slides.add_slide(slide_layout)
    title = slide.shapes.title
    title.text = "Key Initiatives"
    body = slide.placeholders[1]
    tf = body.text_frame
    tf.text = "Launch AI-powered recommendation engine"
    p = tf.add_paragraph()
    p.text = "Expand to 3 new markets (APAC focus)"
    p = tf.add_paragraph()
    p.text = "Achieve SOC 2 Type II compliance"
    p = tf.add_paragraph()
    p.text = "Reduce customer churn by 15%"

    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Budget Allocation"
    body = slide.placeholders[1]
    tf = body.text_frame
    tf.text = "Engineering: $2.5M (45%)"
    for item in ["Marketing: $1.2M (22%)", "Sales: $1.0M (18%)", "Operations: $800K (15%)"]:
        p = tf.add_paragraph()
        p.text = item

    prs.save(filepath("documents", "presentation_final_v2_FINAL.pptx"))

    # Untitled spreadsheet.xlsx
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sales Data"
    headers = ["Month", "Product", "Units Sold", "Revenue ($)", "Region"]
    ws.append(headers)
    data = [
        ["Jan 2023", "Widget Pro", 1250, 62500, "North America"],
        ["Jan 2023", "Widget Lite", 3400, 51000, "Europe"],
        ["Feb 2023", "Widget Pro", 1380, 69000, "North America"],
        ["Feb 2023", "Widget Lite", 3100, 46500, "Europe"],
        ["Mar 2023", "Widget Pro", 1500, 75000, "North America"],
        ["Mar 2023", "Widget Lite", 3650, 54750, "Asia Pacific"],
        ["Apr 2023", "Widget Pro", 1420, 71000, "North America"],
        ["Apr 2023", "Widget Lite", 2900, 43500, "Europe"],
        ["May 2023", "Widget Pro", 1600, 80000, "Asia Pacific"],
        ["May 2023", "Widget Lite", 3200, 48000, "North America"],
    ]
    for row in data:
        ws.append(row)

    ws2 = wb.create_sheet("Summary")
    ws2.append(["Quarter", "Total Revenue", "Growth %"])
    ws2.append(["Q1 2023", "$358,750", "12.3%"])
    ws2.append(["Q2 2023", "$242,500", "8.7%"])

    wb.save(filepath("documents", "Untitled spreadsheet.xlsx"))

    # report.docx
    doc = DocxDocument()
    doc.add_heading("Annual Environmental Impact Report", 0)
    doc.add_heading("Introduction", level=1)
    doc.add_paragraph(
        "This report details the environmental impact assessment conducted for "
        "GreenTech Manufacturing's operations during fiscal year 2023. The assessment "
        "covers carbon emissions, water usage, waste management, and renewable energy adoption."
    )
    doc.add_heading("Carbon Emissions", level=1)
    doc.add_paragraph(
        "Total CO2 emissions decreased by 18% year-over-year, from 12,400 metric tons "
        "to 10,168 metric tons. This reduction was primarily driven by the transition "
        "of our main production facility to solar power in Q2 2023."
    )
    doc.add_heading("Water Usage", level=1)
    doc.add_paragraph(
        "Water consumption was reduced by 22% through the implementation of closed-loop "
        "cooling systems and rainwater harvesting. Total usage: 2.3 million gallons "
        "(down from 2.95 million gallons in 2022)."
    )
    doc.add_heading("Recommendations", level=1)
    doc.add_paragraph(
        "1. Install additional solar panels at the secondary facility\n"
        "2. Implement AI-driven energy management system\n"
        "3. Partner with local recycling cooperatives\n"
        "4. Set science-based targets for 2025"
    )
    doc.save(filepath("documents", "report.docx"))

    print("  documents/ done")


# ============================================================
# AUDIO
# ============================================================
def create_audio():
    print("Creating audio...")

    # recording.mp3 - Minimal valid MP3 frame
    # An MP3 file needs at least one valid frame header
    p = filepath("audio", "recording.mp3")
    with open(p, "wb") as f:
        # ID3v2 tag header
        f.write(b'ID3')           # ID3 identifier
        f.write(b'\x03\x00')     # Version 2.3
        f.write(b'\x00')         # Flags
        f.write(b'\x00\x00\x00\x00')  # Size (0)
        # Write several valid MP3 frames (MPEG1 Layer3, 128kbps, 44100Hz, stereo)
        # Frame header: 0xFFFB9004
        frame_header = b'\xff\xfb\x90\x04'
        # Each frame at 128kbps, 44100Hz is 417 bytes (or 418)
        frame_size = 417
        frame_data = frame_header + b'\x00' * (frame_size - len(frame_header))
        for _ in range(10):  # Write 10 frames
            f.write(frame_data)

    # Voice Memo 001.wav - Valid WAV with a short sine-wave tone
    p = filepath("audio", "Voice Memo 001.wav")
    sample_rate = 44100
    duration = 0.5  # half second
    frequency = 440  # A4 note
    n_samples = int(sample_rate * duration)
    import math
    with wave.open(p, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        for i in range(n_samples):
            value = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
            wf.writeframes(struct.pack("<h", value))

    # track01.flac - Minimal FLAC placeholder with valid magic bytes
    p = filepath("audio", "track01.flac")
    with open(p, "wb") as f:
        f.write(b'fLaC')  # FLAC magic
        # STREAMINFO metadata block (last=1, type=0, length=34)
        f.write(b'\x80\x00\x00\x22')  # last block flag + type 0 + length 34
        # Minimal STREAMINFO: min/max block size, min/max frame size, sample rate, channels, bps, total samples, md5
        f.write(b'\x10\x00')  # min block size = 4096
        f.write(b'\x10\x00')  # max block size = 4096
        f.write(b'\x00\x00\x00')  # min frame size
        f.write(b'\x00\x00\x00')  # max frame size
        # sample rate (20 bits) | channels-1 (3 bits) | bps-1 (5 bits) | total samples (36 bits)
        # 44100 Hz = 0xAC44, channels=2 (1), bps=16 (15)
        f.write(b'\x0A\xC4\x42\xF0')  # sample rate + channels + bps
        f.write(b'\x00\x00\x00\x00')  # total samples (upper)
        f.write(b'\x00' * 16)  # MD5 signature

    print("  audio/ done")


# ============================================================
# VIDEO
# ============================================================
def create_video():
    print("Creating video...")

    # VID_20230915_142233.mp4 - Minimal valid MP4 with ftyp box
    p = filepath("video", "VID_20230915_142233.mp4")
    with open(p, "wb") as f:
        # ftyp box
        ftyp = b'\x00\x00\x00\x20'  # size = 32
        ftyp += b'ftyp'
        ftyp += b'isom'  # major brand
        ftyp += b'\x00\x00\x02\x00'  # minor version
        ftyp += b'isomiso2mp41avc1'  # compatible brands
        f.write(ftyp)
        # mdat box (empty media data)
        mdat = b'\x00\x00\x00\x08' + b'mdat'
        f.write(mdat)
        # moov box (minimal)
        moov_content = b'mvhd' + b'\x00' * 100  # minimal movie header
        moov_size = len(moov_content) + 8
        moov = struct.pack(">I", moov_size) + b'moov' + moov_content
        f.write(moov)

    # Screen Recording 2024-01-15.mov - Minimal QuickTime MOV
    p = filepath("video", "Screen Recording 2024-01-15.mov")
    with open(p, "wb") as f:
        # ftyp box for QuickTime
        ftyp = b'\x00\x00\x00\x14'  # size = 20
        ftyp += b'ftyp'
        ftyp += b'qt  '  # major brand
        ftyp += b'\x00\x00\x00\x00'  # minor version
        f.write(ftyp)
        # moov box (minimal)
        moov_content = b'mvhd' + b'\x00' * 100
        moov_size = len(moov_content) + 8
        moov = struct.pack(">I", moov_size) + b'moov' + moov_content
        f.write(moov)
        # mdat box
        f.write(b'\x00\x00\x00\x08' + b'mdat')

    print("  video/ done")


# ============================================================
# TEXT
# ============================================================
def create_text():
    print("Creating text files...")

    # notes.txt
    with open(filepath("text", "notes.txt"), "w") as f:
        f.write("""Machine Learning Research Notes - Transformer Architecture Experiments
=====================================================================

Date: October 2023
Researcher: Dr. Sarah Chen

Experiment 1: Attention Head Pruning
- Removed 30% of attention heads from BERT-base
- Accuracy drop: only 1.2% on GLUE benchmark
- Inference speedup: 23% on CPU, 18% on GPU
- Conclusion: Significant redundancy exists in multi-head attention

Experiment 2: Sparse Mixture of Experts
- Implemented top-2 gating with 8 expert networks
- Training compute reduced by ~40% vs dense equivalent
- Quality parity achieved at 60% of the FLOPs
- Key insight: Load balancing loss crucial for expert utilization

Experiment 3: Knowledge Distillation with Chain-of-Thought
- Teacher: GPT-4 level model (175B params)
- Student: 7B parameter model
- CoT distillation improved reasoning accuracy by 15% over standard distillation
- Smaller models can learn structured reasoning patterns

TODO:
- [ ] Run ablation study on attention head pruning thresholds
- [ ] Compare MoE routing strategies (hash vs learned vs random)
- [ ] Test distillation with different teacher-student size ratios
- [ ] Write up results for NeurIPS 2024 submission
""")

    # README.md
    with open(filepath("text", "README.md"), "w") as f:
        f.write("""# Nebula Framework

A high-performance distributed computing framework for real-time data processing.

## Overview

Nebula is designed to handle millions of events per second with sub-millisecond
latency. It provides a simple API for building complex data pipelines that scale
horizontally across commodity hardware.

## Features

- **Stream Processing**: Process unbounded data streams with exactly-once semantics
- **Batch Integration**: Seamlessly combine batch and stream processing
- **Auto-scaling**: Dynamically adjust resources based on throughput
- **Fault Tolerance**: Automatic checkpoint and recovery with zero data loss
- **Multi-language SDK**: Python, Java, Go, and Rust clients available

## Quick Start

```python
from nebula import Pipeline, KafkaSource, PostgresSink

pipeline = Pipeline("user-analytics")
pipeline.source(KafkaSource("events-topic"))
pipeline.transform(lambda event: enrich_user_data(event))
pipeline.filter(lambda event: event.type == "purchase")
pipeline.aggregate(window="5m", fn="count", group_by="user_id")
pipeline.sink(PostgresSink("analytics_db", table="purchase_counts"))
pipeline.run()
```

## Architecture

```
┌──────────┐    ┌───────────┐    ┌──────────┐
│  Sources  │───▶│  Workers  │───▶│  Sinks   │
└──────────┘    └───────────┘    └──────────┘
                     │
                ┌────┴────┐
                │  State  │
                │  Store  │
                └─────────┘
```

## Installation

```bash
pip install nebula-framework
```

## License

MIT License - See LICENSE file for details.
""")

    # data.csv
    with open(filepath("text", "data.csv"), "w") as f:
        f.write("""date,ticker,open,high,low,close,volume,market_cap_millions
2023-01-03,AAPL,130.28,130.90,124.17,125.07,112117500,1980000
2023-01-03,MSFT,243.08,245.75,237.40,239.58,25740000,1790000
2023-01-03,GOOGL,89.62,89.98,87.09,89.70,22065700,1160000
2023-01-04,AAPL,126.89,128.66,125.08,126.36,89113600,2000000
2023-01-04,MSFT,240.01,243.31,239.43,229.10,21394400,1710000
2023-01-04,GOOGL,89.17,90.39,88.57,89.87,19622100,1170000
2023-01-05,AAPL,127.13,127.77,124.76,125.02,80962700,1980000
2023-01-05,MSFT,227.20,228.35,225.37,222.31,23783200,1660000
2023-01-05,GOOGL,89.00,89.56,87.10,87.45,22399300,1140000
2023-01-06,AAPL,126.01,130.29,124.89,129.62,87754700,2050000
2023-01-06,MSFT,223.00,225.76,219.35,224.93,25244800,1680000
2023-01-06,GOOGL,87.87,89.43,87.36,88.72,19929600,1160000
2023-01-09,AAPL,130.47,133.41,129.89,130.15,70790800,2060000
2023-01-09,MSFT,225.37,228.50,224.57,227.87,22583000,1700000
2023-01-09,GOOGL,89.06,89.98,88.38,88.98,19926100,1160000
""")

    # config.yaml
    with open(filepath("text", "config.yaml"), "w") as f:
        f.write("""# Application Configuration
# Environment: Production

app:
  name: nebula-api-gateway
  version: 2.4.1
  environment: production
  debug: false
  log_level: info

server:
  host: 0.0.0.0
  port: 8443
  workers: 4
  timeout: 30
  ssl:
    enabled: true
    cert_path: /etc/ssl/certs/server.crt
    key_path: /etc/ssl/private/server.key
    min_version: TLSv1.2

database:
  primary:
    host: db-primary.internal
    port: 5432
    name: nebula_prod
    pool_size: 20
    max_overflow: 10
    ssl_mode: verify-full
  replica:
    host: db-replica.internal
    port: 5432
    name: nebula_prod
    pool_size: 10

cache:
  backend: redis
  host: redis-cluster.internal
  port: 6379
  db: 0
  ttl: 3600
  max_connections: 50

auth:
  provider: oauth2
  issuer: https://auth.example.com
  audience: nebula-api
  token_expiry: 3600
  refresh_expiry: 86400

rate_limiting:
  enabled: true
  requests_per_minute: 1000
  burst_size: 50

monitoring:
  metrics:
    enabled: true
    endpoint: /metrics
    port: 9090
  tracing:
    enabled: true
    provider: jaeger
    sample_rate: 0.1
  health_check:
    endpoint: /health
    interval: 10s
""")

    # app.py
    with open(filepath("text", "app.py"), "w") as f:
        f.write('''#!/usr/bin/env python3
"""
Simple REST API for a todo list application.
Demonstrates basic CRUD operations with Flask.
"""

from flask import Flask, jsonify, request, abort
from datetime import datetime
from uuid import uuid4

app = Flask(__name__)

# In-memory storage
todos = {}


@app.route("/api/todos", methods=["GET"])
def list_todos():
    """List all todo items with optional filtering."""
    status_filter = request.args.get("status")
    items = list(todos.values())
    if status_filter:
        items = [t for t in items if t["status"] == status_filter]
    return jsonify({
        "items": sorted(items, key=lambda x: x["created_at"]),
        "total": len(items),
    })


@app.route("/api/todos", methods=["POST"])
def create_todo():
    """Create a new todo item."""
    data = request.get_json()
    if not data or "title" not in data:
        abort(400, description="Title is required")

    todo = {
        "id": str(uuid4()),
        "title": data["title"],
        "description": data.get("description", ""),
        "status": "pending",
        "priority": data.get("priority", "medium"),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    todos[todo["id"]] = todo
    return jsonify(todo), 201


@app.route("/api/todos/<todo_id>", methods=["PUT"])
def update_todo(todo_id):
    """Update an existing todo item."""
    if todo_id not in todos:
        abort(404, description="Todo not found")

    data = request.get_json()
    todo = todos[todo_id]
    todo.update({
        k: v for k, v in data.items()
        if k in ("title", "description", "status", "priority")
    })
    todo["updated_at"] = datetime.utcnow().isoformat()
    return jsonify(todo)


@app.route("/api/todos/<todo_id>", methods=["DELETE"])
def delete_todo(todo_id):
    """Delete a todo item."""
    if todo_id not in todos:
        abort(404, description="Todo not found")
    del todos[todo_id]
    return "", 204


if __name__ == "__main__":
    app.run(debug=True, port=5000)
''')

    # page.html
    with open(filepath("text", "page.html"), "w") as f:
        f.write("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Company History - Meridian Technologies</title>
    <style>
        body { font-family: Georgia, serif; max-width: 800px; margin: 0 auto; padding: 2rem; color: #333; }
        h1 { color: #1a5276; border-bottom: 3px solid #2980b9; padding-bottom: 0.5rem; }
        h2 { color: #2c3e50; margin-top: 2rem; }
        .timeline { border-left: 3px solid #2980b9; padding-left: 1.5rem; margin-left: 1rem; }
        .year { font-weight: bold; color: #2980b9; font-size: 1.2em; }
        .milestone { margin-bottom: 1.5rem; }
        footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #ccc; color: #777; font-size: 0.9em; }
    </style>
</head>
<body>
    <h1>Our History</h1>
    <p>Meridian Technologies has been at the forefront of innovation since its founding.
       What started as a small software consultancy has grown into a global technology leader.</p>

    <h2>Timeline</h2>
    <div class="timeline">
        <div class="milestone">
            <span class="year">1998</span>
            <p>Founded in a garage in Palo Alto by Maria Chen and David Okafor.
               Initial focus on database optimization consulting.</p>
        </div>
        <div class="milestone">
            <span class="year">2003</span>
            <p>Launched MeridianDB, our flagship distributed database product.
               Secured Series A funding of $5M from Sequoia Capital.</p>
        </div>
        <div class="milestone">
            <span class="year">2008</span>
            <p>Expanded to European markets. Opened offices in London and Berlin.
               Employee count surpassed 500.</p>
        </div>
        <div class="milestone">
            <span class="year">2015</span>
            <p>IPO on NASDAQ. Launched cloud-native platform MeridianCloud.
               Named to Forbes Cloud 100 list.</p>
        </div>
        <div class="milestone">
            <span class="year">2023</span>
            <p>Acquired DataStream Analytics for $2.1B. Launched AI-powered
               data platform. Revenue exceeded $4B annually.</p>
        </div>
    </div>

    <footer>
        <p>&copy; 2023 Meridian Technologies, Inc. All rights reserved.</p>
    </footer>
</body>
</html>
""")

    print("  text/ done")


# ============================================================
# MIXED FOLDER
# ============================================================
def create_mixed_folder():
    print("Creating mixed-folder files...")

    # IMG_001.jpg - tiny JPEG
    img = Image.new("RGB", (10, 10), color=(255, 200, 100))
    img.save(filepath("mixed-folder", "IMG_001.jpg"), "JPEG")

    # meeting-notes.txt
    with open(filepath("mixed-folder", "meeting-notes.txt"), "w") as f:
        f.write("""Project Phoenix - Sprint Planning Meeting
Date: November 20, 2023
Attendees: Sarah, Mike, Priya, James, Lin

Agenda:
1. Sprint 14 Retrospective
2. Sprint 15 Planning
3. Q4 Release Timeline

Key Discussion Points:

Sprint 14 Retro:
- Completed 34 of 38 story points (89% completion rate)
- Two critical bugs found in production - auth token refresh race condition
- Mike's team successfully migrated 80% of users to new billing system
- Action item: Priya to set up additional monitoring for auth service

Sprint 15 Planning:
- Priority 1: Fix remaining auth race condition (8 pts - James)
- Priority 2: Complete billing migration for enterprise tier (13 pts - Mike)
- Priority 3: Implement new dashboard analytics (8 pts - Lin)
- Priority 4: API rate limiting improvements (5 pts - Sarah)
- Total committed: 34 story points

Q4 Release:
- Target date: December 15, 2023
- Feature freeze: December 1
- All teams need to complete integration testing by Dec 8
- Marketing materials due by Dec 10

Action Items:
- [ ] Sarah: Schedule load testing for rate limiter
- [ ] Mike: Share billing migration runbook
- [ ] Priya: Deploy auth monitoring dashboard
- [ ] James: Write postmortem for auth incident
- [ ] Lin: Create mockups for dashboard v2

Next meeting: November 27, 2023
""")

    # budget.csv
    with open(filepath("mixed-folder", "budget.csv"), "w") as f:
        f.write("""department,category,q1_budget,q1_actual,q2_budget,q2_actual,q3_budget,q3_actual,q4_budget,notes
Engineering,Salaries,850000,842000,875000,871000,900000,895000,920000,Includes 3 new hires in Q3
Engineering,Cloud Infrastructure,120000,135000,130000,142000,140000,155000,150000,Over budget due to traffic spike
Engineering,Software Licenses,45000,43000,45000,47000,50000,48000,50000,
Marketing,Advertising,200000,195000,250000,268000,300000,285000,350000,Q4 includes holiday campaign
Marketing,Events & Conferences,80000,72000,60000,58000,40000,35000,100000,AWS re:Invent in Q4
Marketing,Content Production,35000,33000,35000,37000,40000,42000,45000,
Sales,Commissions,180000,195000,190000,210000,200000,225000,220000,Exceeding targets consistently
Sales,Travel,60000,55000,65000,70000,70000,68000,75000,
Sales,Tools & CRM,25000,24000,25000,25000,28000,28000,28000,
Operations,Office Lease,90000,90000,90000,90000,95000,95000,95000,Renewal in Q3 with 5% increase
Operations,Utilities & Supplies,15000,14000,15000,13500,16000,15000,16000,
HR,Recruiting,40000,52000,35000,45000,30000,38000,25000,High demand for senior engineers
HR,Training & Development,20000,18000,22000,20000,25000,23000,28000,
""")

    # logo.svg
    with open(filepath("mixed-folder", "logo.svg"), "w") as f:
        f.write("""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200" height="200">
  <defs>
    <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#2980b9;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#8e44ad;stop-opacity:1" />
    </linearGradient>
  </defs>
  <circle cx="100" cy="100" r="90" fill="url(#grad1)" />
  <text x="100" y="115" font-family="Arial, sans-serif" font-size="48" font-weight="bold"
        fill="white" text-anchor="middle">M</text>
  <circle cx="100" cy="100" r="90" fill="none" stroke="white" stroke-width="4" opacity="0.3" />
</svg>
""")

    print("  mixed-folder/ done")


# ============================================================
# EDGE CASES
# ============================================================
def create_edge_cases():
    print("Creating edge-case files...")

    # .hidden-file.txt
    with open(filepath("edge-cases", ".hidden-file.txt"), "w") as f:
        f.write("""This is a hidden file (starts with a dot).
It might contain sensitive configuration or notes that
the user doesn't want visible in normal directory listings.

Common examples of hidden files:
- .env (environment variables)
- .gitignore (git ignore rules)
- .bashrc (shell configuration)
- .ssh/config (SSH configuration)

This file tests whether the rename tool properly handles
files whose names begin with a period.
""")

    # CON.txt - Windows reserved name
    with open(filepath("edge-cases", "CON.txt"), "w") as f:
        f.write("""This file is named CON.txt, which is a reserved device name on Windows.

Windows reserved names include:
CON, PRN, AUX, NUL, COM1-COM9, LPT1-LPT9

These names cannot be used as file names on Windows regardless
of the file extension. A good rename tool should detect and
handle these appropriately when targeting cross-platform compatibility.

This file tests the tool's ability to identify potentially
problematic filenames for Windows systems.
""")

    # file with   lots   of   spaces.txt
    with open(filepath("edge-cases", "file with   lots   of   spaces.txt"), "w") as f:
        f.write("""This file has excessive whitespace in its name.
Multiple consecutive spaces between words can cause issues with:
- Command-line tools that split on whitespace
- Scripts that don't properly quote file paths
- URL encoding in web applications
- Certain backup and sync tools

A good rename tool should normalize the spacing in filenames.
""")

    # UPPERCASE_NAME.PDF
    with open(filepath("edge-cases", "UPPERCASE_NAME.PDF"), "w") as f:
        f.write("""This file has an all-uppercase name and extension.
While technically valid on most file systems, it violates
common naming conventions. The .PDF extension (uppercase)
should ideally be normalized to .pdf (lowercase).

This tests whether the rename tool normalizes file extensions
and converts overly aggressive capitalization.
""")

    # cafe-resume.txt (Unicode characters)
    with open(filepath("edge-cases", "café-résumé.txt"), "w", encoding="utf-8") as f:
        f.write("""This file contains Unicode characters in its name:
- é (e with acute accent)
- Both in "café" and "résumé"

Unicode filenames can cause issues with:
- Older file systems (FAT32)
- Some command-line tools
- Cross-platform file sharing
- NFC vs NFD normalization (especially on macOS)
- URL encoding in web applications

The rename tool should decide whether to preserve, transliterate,
or strip non-ASCII characters based on its configuration.
""")

    # Very long filename
    long_name = "this-is-an-extremely-long-file-name-that-goes-on-and-on-and-on-and-on-and-keeps-going-to-test-the-length-limit-of-our-naming-system-which-should-truncate-appropriately.txt"
    with open(filepath("edge-cases", long_name), "w") as f:
        f.write("""This file has an extremely long name (168 characters including extension).

Most file systems have limits:
- ext4: 255 bytes
- NTFS: 255 characters
- HFS+: 255 characters
- Full path limit on Windows: 260 characters (MAX_PATH)

The rename tool should respect these limits and truncate
intelligently rather than at arbitrary positions.
""")

    # no_extension
    with open(filepath("edge-cases", "no_extension"), "w") as f:
        f.write("""This file has no file extension at all.
The rename tool needs to handle files without extensions gracefully.

Without an extension, the tool must:
1. Detect the file type from content/magic bytes
2. Decide whether to add an appropriate extension
3. Generate a descriptive name without relying on extension hints

This is a plain text file that could be identified by:
- MIME type detection (text/plain)
- Magic byte analysis
- Content inspection
""")

    # empty-file.txt
    with open(filepath("edge-cases", "empty-file.txt"), "w") as f:
        pass  # truly empty

    # file_with_bad_chars.txt
    with open(filepath("edge-cases", "file_with_bad_chars.txt"), "w") as f:
        f.write("""This file tests handling of problematic characters in filenames.

The original intended name was: file<with>bad:chars.txt
Characters that are illegal in filenames on various OS:
- Windows: \\ / : * ? " < > |
- macOS: / and : (: shows as / in Finder)
- Linux: / and null byte

The rename tool should sanitize filenames by:
1. Removing or replacing illegal characters
2. Maintaining readability
3. Preserving the file extension
4. Avoiding collisions with existing files
""")

    # unnamed - binary-like content
    p = filepath("edge-cases", "unnamed")
    with open(p, "wb") as f:
        random.seed(42)  # reproducible
        f.write(bytes(random.getrandbits(8) for _ in range(512)))

    print("  edge-cases/ done")


# ============================================================
# NESTED
# ============================================================
def create_nested():
    print("Creating nested files...")

    # nested/level1/deep-file-1.txt
    with open(filepath("nested", "level1", "deep-file-1.txt"), "w") as f:
        f.write("""Level 1 Document - Project Architecture Overview

This document describes the high-level architecture of the
distributed processing system deployed across three data centers.

Components:
1. API Gateway (this level)
   - Rate limiting
   - Authentication
   - Request routing

2. Processing Layer (level 2)
   - Worker nodes
   - Task queue
   - Load balancer

3. Storage Layer (level 3)
   - Primary database
   - Object storage
   - Cache cluster

This file exists at the first level of nesting to test how
the rename tool handles files in deeply nested directory structures.
""")

    # nested/level1/level2/deep-file-2.pdf
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 20, "Level 2 Technical Specification", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.ln(10)
    pdf.multi_cell(0, 7, (
        "This document contains the technical specifications for the processing layer.\n\n"
        "Worker Node Requirements:\n"
        "- CPU: 8 cores minimum\n"
        "- RAM: 32GB minimum\n"
        "- Storage: 500GB NVMe SSD\n"
        "- Network: 10Gbps\n\n"
        "Task Queue Configuration:\n"
        "- Backend: RabbitMQ 3.12\n"
        "- Max queue depth: 100,000 messages\n"
        "- Message TTL: 24 hours\n"
        "- Dead letter exchange enabled"
    ))
    pdf.output(filepath("nested", "level1", "level2", "deep-file-2.pdf"))

    # nested/level1/level2/level3/deep-file-3.txt
    with open(filepath("nested", "level1", "level2", "level3", "deep-file-3.txt"), "w") as f:
        f.write("""Deepest Level Document - Storage Layer Configuration

This is the deepest file in the nested directory structure,
located at level 3 of nesting.

Database Configuration:
  Primary: PostgreSQL 15.4
    - Host: db-primary-01.internal
    - Port: 5432
    - Max connections: 200
    - Shared buffers: 8GB
    - Effective cache size: 24GB

  Replicas: 3 read replicas
    - Async replication lag target: <100ms
    - Auto-failover: enabled

Object Storage:
  Provider: MinIO (S3-compatible)
  Buckets:
    - raw-data: incoming unprocessed files
    - processed: transformation outputs
    - archives: long-term storage (lifecycle: 90 days -> Glacier)

Cache:
  Redis Cluster: 6 nodes (3 primary + 3 replica)
  Memory per node: 16GB
  Eviction policy: allkeys-lru
""")

    print("  nested/ done")


# ============================================================
# ALREADY WELL-NAMED
# ============================================================
def create_already_well_named():
    print("Creating already-well-named files...")

    # quarterly-revenue-report-2023.pdf
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 20, "Quarterly Revenue Report 2023", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 12)
    pdf.ln(10)
    pdf.multi_cell(0, 8, (
        "Annual Summary\n\n"
        "Q1: $3.8M (Budget: $3.5M) - 108.6% of target\n"
        "Q2: $4.1M (Budget: $4.0M) - 102.5% of target\n"
        "Q3: $4.2M (Budget: $4.2M) - 100.0% of target\n"
        "Q4: $5.1M (Budget: $4.5M) - 113.3% of target\n\n"
        "Full Year: $17.2M (Budget: $16.2M) - 106.2% of target\n\n"
        "This file is already well-named and should not be renamed."
    ))
    pdf.output(filepath("already-well-named", "quarterly-revenue-report-2023.pdf"))

    # sunset-over-golden-gate-bridge.jpg
    # Create a simple gradient image suggesting a sunset
    img = Image.new("RGB", (20, 20))
    for y in range(20):
        for x in range(20):
            r = min(255, 255 - y * 5)
            g = max(0, 100 - y * 5)
            b = max(0, 50 + y * 5)
            img.putpixel((x, y), (r, g, b))
    img.save(filepath("already-well-named", "sunset-over-golden-gate-bridge.jpg"), "JPEG")

    # meeting-notes-project-alpha.txt
    with open(filepath("already-well-named", "meeting-notes-project-alpha.txt"), "w") as f:
        f.write("""Meeting Notes - Project Alpha
Date: September 5, 2023
Location: Conference Room B

Attendees: Team Alpha (full team)

Status Update:
- Backend API: 90% complete, remaining endpoint for batch processing
- Frontend: 75% complete, dashboard components in review
- Infrastructure: CI/CD pipeline fully operational
- Documentation: API docs auto-generated, user guide in progress

This file is already well-named using the recommended format:
topic-subject-identifier.extension

The rename tool should recognize this as a well-named file
and either skip it or confirm the name is already appropriate.
""")

    print("  already-well-named/ done")


# ============================================================
# UNSUPPORTED
# ============================================================
def create_unsupported():
    print("Creating unsupported files...")

    # archive.zip - valid zip with a small text file inside
    p = filepath("unsupported", "archive.zip")
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("readme.txt", "This is a text file inside a zip archive.\n"
                     "The zip contains sample data for testing.\n")
        zf.writestr("data/sample.csv", "id,name,value\n1,alpha,100\n2,beta,200\n3,gamma,300\n")

    # database.sqlite - tiny SQLite database
    p = filepath("unsupported", "database.sqlite")
    conn = sqlite3.connect(p)
    c = conn.cursor()
    c.execute("""CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("INSERT INTO users (name, email) VALUES ('Alice Johnson', 'alice@example.com')")
    c.execute("INSERT INTO users (name, email) VALUES ('Bob Smith', 'bob@example.com')")
    c.execute("INSERT INTO users (name, email) VALUES ('Carol Williams', 'carol@example.com')")
    c.execute("""CREATE TABLE posts (
        id INTEGER PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        title TEXT,
        body TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("INSERT INTO posts (user_id, title, body) VALUES (1, 'Hello World', 'My first post on this platform.')")
    c.execute("INSERT INTO posts (user_id, title, body) VALUES (2, 'Getting Started', 'A guide for new users.')")
    conn.commit()
    conn.close()

    # program.exe - minimal PE header placeholder
    p = filepath("unsupported", "program.exe")
    with open(p, "wb") as f:
        # DOS header
        f.write(b'MZ')  # DOS signature
        f.write(b'\x90' * 58)  # padding
        f.write(struct.pack("<I", 64))  # offset to PE header at 64
        # Pad to offset 64
        f.write(b'\x00' * (64 - 64))  # already at 64
        # PE signature
        f.write(b'PE\x00\x00')
        # Minimal COFF header
        f.write(struct.pack("<HH", 0x14C, 0))  # i386 machine, 0 sections
        f.write(b'\x00' * 16)  # timestamp, symbol table, etc.
        # Padding
        f.write(b'\x00' * 128)

    # model.obj - simple 3D model in OBJ format (a cube)
    with open(filepath("unsupported", "model.obj"), "w") as f:
        f.write("""# Simple cube model
# Exported from Blender 3.6
# Vertices: 8, Faces: 6

o Cube

# Vertices
v -1.0 -1.0  1.0
v  1.0 -1.0  1.0
v  1.0  1.0  1.0
v -1.0  1.0  1.0
v -1.0 -1.0 -1.0
v  1.0 -1.0 -1.0
v  1.0  1.0 -1.0
v -1.0  1.0 -1.0

# Texture coordinates
vt 0.0 0.0
vt 1.0 0.0
vt 1.0 1.0
vt 0.0 1.0

# Normals
vn  0.0  0.0  1.0
vn  0.0  0.0 -1.0
vn  1.0  0.0  0.0
vn -1.0  0.0  0.0
vn  0.0  1.0  0.0
vn  0.0 -1.0  0.0

# Faces
f 1/1/1 2/2/1 3/3/1 4/4/1
f 5/1/2 8/2/2 7/3/2 6/4/2
f 2/1/3 6/2/3 7/3/3 3/4/3
f 1/1/4 4/2/4 8/3/4 5/4/4
f 4/1/5 3/2/5 7/3/5 8/4/5
f 1/1/6 5/2/6 6/3/6 2/4/6
""")

    print("  unsupported/ done")


# ============================================================
# SYMLINKS
# ============================================================
def create_symlinks():
    print("Creating symlinks...")

    # real-file.txt
    with open(filepath("symlinks", "real-file.txt"), "w") as f:
        f.write("""This is the real file that symlinks point to.

Symlinks (symbolic links) are special files that act as
references to another file. The rename tool needs to handle
symlinks carefully:

1. Should it rename the symlink or the target?
2. Should it follow symlinks or skip them?
3. What happens if a symlink is broken (dangling)?
4. Should the tool preserve symlink relationships?

This file tests all of these scenarios.
""")

    # Create symlinks
    symlink_dir = os.path.join(BASE, "symlinks")
    link1 = os.path.join(symlink_dir, "link-to-real.txt")
    link2 = os.path.join(symlink_dir, "another-link.txt")

    # Remove existing symlinks if present
    for link in [link1, link2]:
        if os.path.islink(link) or os.path.exists(link):
            os.remove(link)

    os.symlink("real-file.txt", link1)
    os.symlink("real-file.txt", link2)

    print("  symlinks/ done")


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"Generating test fixtures in: {BASE}")
    print("=" * 60)

    create_images()
    create_documents()
    create_audio()
    create_video()
    create_text()
    create_mixed_folder()
    create_edge_cases()
    create_nested()
    create_already_well_named()
    create_unsupported()
    create_symlinks()

    print("=" * 60)
    print("All fixtures created successfully!")

    # Print summary
    total = 0
    for root, dirs, files in os.walk(BASE):
        for f in files:
            total += 1
            rel = os.path.relpath(os.path.join(root, f), BASE)
            size = os.path.getsize(os.path.join(root, f))
            is_link = " -> " + os.readlink(os.path.join(root, f)) if os.path.islink(os.path.join(root, f)) else ""
            print(f"  {rel} ({size:,} bytes){is_link}")

    print(f"\nTotal files created: {total}")


if __name__ == "__main__":
    main()
