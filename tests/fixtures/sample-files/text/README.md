# Nebula Framework

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
