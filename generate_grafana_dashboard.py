"""
Generate a Grafana dashboard JSON from the Streamlit artifact_jobs_dashboard.py logic.
Uses the grafana-mongodb-datasource plugin and mirrors all panels/queries.
"""

import json
import os

DATASOURCE = {"type": "grafana-mongodb-datasource", "uid": "bf98gc6lkomioc"}
COLLECTION = "artifactJobs"
PLUGIN_VERSION = "12.4.0-21959849188.patch2"

artifact_types_path = os.path.join(os.path.dirname(__file__), "artifactTypes.json")
with open(artifact_types_path) as f:
    ARTIFACT_TYPES = json.load(f)

STATUS_COLOR_OVERRIDES = [
    {"matcher": {"id": "byName", "options": s}, "properties": [{"id": "color", "value": {"fixedColor": c, "mode": "fixed"}}]}
    for s, c in [("completed", "green"), ("running", "purple"), ("failed", "red"), ("cancelled", "yellow"), ("pending", "blue")]
]

def _switch_branches(id_expr="$_id"):
    return [
        {"case": {"$eq": [{"$toString": id_expr}, oid]}, "then": name}
        for oid, name in ARTIFACT_TYPES.items()
    ]

def _artifact_name_switch(id_expr="$_id"):
    return {"$switch": {"branches": _switch_branches(id_expr), "default": {"$toString": id_expr}}}

def _base_match():
    """Time filter only. Artifact type filtering added via _type_filter_stages()."""
    return {"createdAt": {"$gte": "$__timeFrom", "$lte": "$__timeTo"}}


TYPE_FILTER_PLACEHOLDER = "__TYPE_FILTER_STAGES__"

def _type_filter_stages_json():
    """Raw JSON for the $addFields + $match stages that filter by artifact type.

    Uses $addFields to compute a boolean, then $match on it.
    When allValue="all", the first $eq is true and everything passes.
    When a specific hex OID is selected, the second $eq matches by toString.
    Variable "$_artifact_type" is inside quotes so the plugin substitutes
    only the content (a plain hex string or "all").
    """
    return """
  {
    "$addFields": {
      "__passesTypeFilter": {
        "$or": [
          {"$eq": ["$_artifact_type", "all"]},
          {"$eq": [{"$toString": "$artifactTypeId"}, "$_artifact_type"]}
        ]
      }
    }
  },
  {
    "$match": {"__passesTypeFilter": true}
  }"""


def _build_artifact_type_variable():
    """Build a Grafana custom variable for artifact type filtering.

    Values are plain hex OID strings (no JSON wrapping needed).
    allValue="all" triggers the pass-all branch in the $addFields filter.
    """
    options = [{"selected": True, "text": "All", "value": "$__all"}]
    query_parts = []
    for oid, name in ARTIFACT_TYPES.items():
        options.append({"selected": False, "text": name, "value": oid})
        query_parts.append(f"{name} : {oid}")
    return {
        "current": {"selected": True, "text": "All", "value": "$__all"},
        "description": "Filter all panels by a specific artifact type",
        "hide": 0,
        "includeAll": True,
        "allValue": "all",
        "label": "Artifact Type",
        "multi": False,
        "name": "_artifact_type",
        "options": options,
        "query": ",".join(query_parts),
        "skipUrlSync": False,
        "type": "custom",
    }


def _mongo_query(pipeline):
    raw = f"db.{COLLECTION}.aggregate({json.dumps(pipeline, indent=2)})"
    raw = raw.replace(f'"{TYPE_FILTER_PLACEHOLDER}"', _type_filter_stages_json())
    return raw

def _with_type_filter(pipeline):
    """Insert type filter placeholder after the first $match stage."""
    return [pipeline[0], TYPE_FILTER_PLACEHOLDER] + pipeline[1:]

def _target(pipeline, ref="A"):
    q = _mongo_query(_with_type_filter(pipeline))
    return {"datasource": DATASOURCE, "parsedQuery": q, "query": q, "queryType": "query", "refId": ref}


def stat_panel(title, pipeline, grid, panel_id, thresholds=None, unit="locale", decimals=0, color_mode="value"):
    steps = thresholds or [{"color": "green", "value": 0}]
    return {
        "datasource": DATASOURCE,
        "fieldConfig": {
            "defaults": {"color": {"mode": "thresholds"}, "decimals": decimals, "mappings": [],
                         "thresholds": {"mode": "absolute", "steps": steps}, "unit": unit},
            "overrides": []
        },
        "gridPos": grid, "id": panel_id,
        "options": {"colorMode": color_mode, "graphMode": "area", "justifyMode": "auto", "orientation": "auto",
                    "percentChangeColorMode": "standard",
                    "reduceOptions": {"calcs": ["sum"], "fields": "", "values": False},
                    "showPercentChange": False, "textMode": "auto", "wideLayout": True},
        "pluginVersion": PLUGIN_VERSION,
        "targets": [_target(pipeline)],
        "title": title, "type": "stat"
    }


def pie_panel(title, pipeline, grid, panel_id):
    return {
        "datasource": DATASOURCE,
        "fieldConfig": {
            "defaults": {"color": {"mode": "palette-classic"}, "custom": {"hideFrom": {"legend": False, "tooltip": False, "viz": False}},
                         "decimals": 0, "mappings": [], "unit": "locale"},
            "overrides": STATUS_COLOR_OVERRIDES
        },
        "gridPos": grid, "id": panel_id,
        "options": {"legend": {"displayMode": "table", "placement": "bottom", "showLegend": True, "values": ["value"]},
                    "pieType": "pie",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
                    "sort": "desc",
                    "tooltip": {"hideZeros": False, "mode": "single", "sort": "none"}},
        "pluginVersion": PLUGIN_VERSION,
        "targets": [_target(pipeline)],
        "title": title, "type": "piechart"
    }


def timeseries_panel(title, pipeline, grid, panel_id, draw_style="line", fill=10, stacking="none",
                     legend_placement="bottom", overrides=None, y_axis_label="", thresholds_steps=None):
    steps = thresholds_steps or [{"color": "green", "value": 0}, {"color": "red", "value": 80}]
    return {
        "datasource": DATASOURCE,
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "palette-classic"},
                "custom": {
                    "axisBorderShow": False, "axisCenteredZero": False, "axisColorMode": "text",
                    "axisLabel": y_axis_label, "axisPlacement": "auto", "barAlignment": 0, "barWidthFactor": 0.6,
                    "drawStyle": draw_style, "fillOpacity": fill, "gradientMode": "none",
                    "hideFrom": {"legend": False, "tooltip": False, "viz": False},
                    "insertNulls": False, "lineInterpolation": "linear", "lineWidth": 1, "pointSize": 5,
                    "scaleDistribution": {"type": "linear"}, "showPoints": "auto", "showValues": False,
                    "spanNulls": False, "stacking": {"group": "A", "mode": stacking},
                    "thresholdsStyle": {"mode": "off"}
                },
                "decimals": 0, "mappings": [],
                "thresholds": {"mode": "absolute", "steps": steps},
                "unit": "locale"
            },
            "overrides": overrides or STATUS_COLOR_OVERRIDES
        },
        "gridPos": grid, "id": panel_id,
        "options": {
            "legend": {"calcs": ["sum"], "displayMode": "table", "placement": legend_placement, "showLegend": True},
            "tooltip": {"hideZeros": False, "mode": "multi", "sort": "desc"}
        },
        "pluginVersion": PLUGIN_VERSION,
        "targets": [_target(pipeline)],
        "title": title, "type": "timeseries"
    }


def table_panel(title, pipeline, grid, panel_id, overrides=None, transformations=None):
    return {
        "datasource": DATASOURCE,
        "fieldConfig": {
            "defaults": {"color": {"mode": "thresholds"}, "custom": {"align": "auto", "cellOptions": {"type": "auto"}, "inspect": False},
                         "mappings": [], "thresholds": {"mode": "absolute", "steps": [{"color": "green"}]}},
            "overrides": overrides or []
        },
        "gridPos": grid, "id": panel_id,
        "options": {"cellHeight": "sm", "showHeader": True},
        "pluginVersion": PLUGIN_VERSION,
        "targets": [_target(pipeline)],
        "title": title, "type": "table",
        "transformations": transformations or []
    }


def barchart_panel(title, pipeline, grid, panel_id, orientation="horizontal", x_field=None):
    opts = {
        "barWidth": 0.7, "fullHighlight": False, "groupWidth": 0.7,
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
        "orientation": orientation,
        "tooltip": {"mode": "multi", "sort": "desc"},
        "showValue": "auto", "stacking": "off"
    }
    if x_field:
        opts["xField"] = x_field
    return {
        "datasource": DATASOURCE,
        "fieldConfig": {
            "defaults": {"color": {"mode": "palette-classic"}, "mappings": [],
                         "thresholds": {"mode": "absolute", "steps": [{"color": "green"}]}},
            "overrides": []
        },
        "gridPos": grid, "id": panel_id,
        "options": opts,
        "pluginVersion": PLUGIN_VERSION,
        "targets": [_target(pipeline)],
        "title": title, "type": "barchart"
    }


def row_panel(title, grid, panel_id, collapsed=False):
    return {
        "collapsed": collapsed, "gridPos": grid, "id": panel_id,
        "panels": [], "title": title, "type": "row"
    }


def text_panel(html, grid, panel_id):
    return {
        "fieldConfig": {"defaults": {}, "overrides": []},
        "gridPos": grid, "id": panel_id,
        "options": {"code": {"language": "plaintext", "showLineNumbers": False, "showMiniMap": False},
                    "content": html, "mode": "html"},
        "pluginVersion": PLUGIN_VERSION, "title": "", "type": "text"
    }



# ── Build panels ──

panels = []
pid = 1
y = 0

# ─── Header ───
panels.append(text_panel(
    '\n<div style="padding: 20px;">\n'
    '  <div style="display: flex; justify-content: space-between; align-items: center; margin: 0 0 16px 0;">\n'
    '    <h1 style="font-size: 2.5em; font-weight: bold; margin: 0; line-height: 1.2;">Artifact Jobs Monitoring Dashboard</h1>\n'
    '    <span style="background: #5794f2; color: #ffffff; padding: 4px 12px; border-radius: 12px; font-size: 0.9em; '
    'font-weight: 500; text-transform: uppercase;">production</span>\n'
    '  </div>\n'
    '  <p style="font-size: 1.1em; margin: 0; color: #b7b7b7; line-height: 1.5;">'
    'Real-time monitoring of job statuses, errors, and trends</p>\n'
    '</div>\n',
    {"h": 4, "w": 24, "x": 0, "y": y}, pid
))
pid += 1; y += 4

# ─── Metrics row (6 stat panels, w=4 each) ───

# Total Jobs
panels.append(stat_panel("Total Jobs", [
    {"$match": {**_base_match()}},
    {"$group": {"_id": {"$dateTrunc": {"date": "$createdAt", "unit": "hour"}}, "count": {"$sum": 1}}},
    {"$sort": {"_id": 1}},
    {"$project": {"time": "$_id", "value": "$count", "_id": 0}}
], {"h": 6, "w": 4, "x": 0, "y": y}, pid))
pid += 1

# Completed
panels.append(stat_panel("Completed", [
    {"$match": {"status": "completed", **_base_match()}},
    {"$group": {"_id": {"$dateTrunc": {"date": "$createdAt", "unit": "hour"}}, "count": {"$sum": 1}}},
    {"$sort": {"_id": 1}},
    {"$project": {"time": "$_id", "value": "$count", "_id": 0}}
], {"h": 6, "w": 4, "x": 4, "y": y}, pid,
    thresholds=[{"color": "green", "value": 0}]))
pid += 1

# Failed
panels.append(stat_panel("Failed", [
    {"$match": {"status": "failed", **_base_match()}},
    {"$group": {"_id": {"$dateTrunc": {"date": "$createdAt", "unit": "hour"}}, "count": {"$sum": 1}}},
    {"$sort": {"_id": 1}},
    {"$project": {"time": "$_id", "value": "$count", "_id": 0}}
], {"h": 6, "w": 4, "x": 8, "y": y}, pid,
    thresholds=[{"color": "green", "value": 0}, {"color": "orange", "value": 10}, {"color": "red", "value": 50}]))
pid += 1

# Health %
panels.append(stat_panel("Health %", [
    {"$match": {**_base_match()}},
    {"$group": {"_id": None, "total": {"$sum": 1},
                "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}}}},
    {"$project": {"value": {"$round": [{"$subtract": [100, {"$multiply": [{"$divide": ["$failed", "$total"]}, 100]}]}, 1]}, "_id": 0}}
], {"h": 6, "w": 4, "x": 12, "y": y}, pid,
    thresholds=[{"color": "red", "value": 0}, {"color": "orange", "value": 80}, {"color": "green", "value": 95}],
    unit="percent", decimals=1))
pid += 1

# Avg Duration (minutes)
panels.append(stat_panel("Avg Duration", [
    {"$match": {**_base_match(), "execution.totalDuration": {"$exists": True, "$gt": 0}}},
    {"$group": {"_id": None, "avgDuration": {"$avg": "$execution.totalDuration"}}},
    {"$project": {"value": {"$round": [{"$divide": ["$avgDuration", 60]}, 1]}, "_id": 0}}
], {"h": 6, "w": 4, "x": 16, "y": y}, pid, unit="m", decimals=1))
pid += 1

# Avg Pending Time (seconds)
panels.append(stat_panel("Avg Pending Time", [
    {"$match": {**_base_match(), "startTime": {"$exists": True}}},
    {"$project": {"pendingMs": {"$subtract": ["$startTime", "$createdAt"]}}},
    {"$match": {"pendingMs": {"$gt": 0}}},
    {"$group": {"_id": None, "avgPending": {"$avg": "$pendingMs"}}},
    {"$project": {"value": {"$round": [{"$divide": ["$avgPending", 1000]}, 1]}, "_id": 0}}
], {"h": 6, "w": 4, "x": 20, "y": y}, pid, unit="s", decimals=1))
pid += 1; y += 6

# ─── Jobs Over Time (timeseries) + Status Distribution (piechart) ───

panels.append(timeseries_panel("Jobs Over Time", [
    {"$match": {**_base_match()}},
    {"$group": {"_id": {"time": {"$dateTrunc": {"date": "$createdAt", "unit": "hour"}}, "status": "$status"}, "count": {"$sum": 1}}},
    {"$sort": {"_id.time": 1}},
    {"$project": {"time": "$_id.time", "status": "$_id.status", "value": "$count", "_id": 0}}
], {"h": 12, "w": 16, "x": 0, "y": y}, pid, draw_style="bars", stacking="normal"))
pid += 1

panels.append(pie_panel("Status Distribution", [
    {"$match": {**_base_match()}},
    {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    {"$project": {"status": "$_id", "value": "$count", "_id": 0}}
], {"h": 12, "w": 8, "x": 16, "y": y}, pid))
pid += 1; y += 12

# ─── Failure Rate Over Time ───

panels.append(timeseries_panel("Failure Rate Over Time (%)", [
    {"$match": {**_base_match()}},
    {"$group": {"_id": {"$dateTrunc": {"date": "$createdAt", "unit": "hour"}},
                "total": {"$sum": 1},
                "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}}}},
    {"$sort": {"_id": 1}},
    {"$project": {"time": "$_id",
                  "value": {"$round": [{"$cond": [{"$gt": ["$total", 0]}, {"$multiply": [{"$divide": ["$failed", "$total"]}, 100]}, 0]}, 1]},
                  "_id": 0}}
], {"h": 10, "w": 24, "x": 0, "y": y}, pid,
    overrides=[{"matcher": {"id": "byName", "options": "value"}, "properties": [{"id": "color", "value": {"fixedColor": "red", "mode": "fixed"}}, {"id": "displayName", "value": "Failure Rate %"}]}],
    y_axis_label="Failure Rate %"))
pid += 1; y += 10

# ─── Average Duration Over Time ───

panels.append(timeseries_panel("Average Duration Over Time (minutes)", [
    {"$match": {**_base_match(), "execution.totalDuration": {"$exists": True, "$gt": 0}}},
    {"$group": {"_id": {"$dateTrunc": {"date": "$createdAt", "unit": "hour"}},
                "avgDuration": {"$avg": "$execution.totalDuration"},
                "count": {"$sum": 1}}},
    {"$sort": {"_id": 1}},
    {"$project": {"time": "$_id",
                  "value": {"$round": [{"$divide": ["$avgDuration", 60]}, 1]},
                  "_id": 0}}
], {"h": 10, "w": 24, "x": 0, "y": y}, pid,
    overrides=[{"matcher": {"id": "byName", "options": "value"}, "properties": [{"id": "color", "value": {"fixedColor": "blue", "mode": "fixed"}}, {"id": "displayName", "value": "Avg Duration (min)"}]}],
    y_axis_label="Minutes"))
pid += 1; y += 10

# ─── Pending Jobs Over Time ───

panels.append(timeseries_panel("Pending Jobs Over Time", [
    {"$match": {**_base_match(), "status": "pending"}},
    {"$group": {"_id": {"$dateTrunc": {"date": "$createdAt", "unit": "hour"}},
                "count": {"$sum": 1}}},
    {"$sort": {"_id": 1}},
    {"$project": {"time": "$_id", "value": "$count", "_id": 0}}
], {"h": 10, "w": 24, "x": 0, "y": y}, pid,
    overrides=[{"matcher": {"id": "byName", "options": "value"}, "properties": [{"id": "color", "value": {"fixedColor": "orange", "mode": "fixed"}}, {"id": "displayName", "value": "Pending Jobs"}]}],
    y_axis_label="Jobs"))
pid += 1; y += 10

# ─── Error Analysis Row ───

panels.append(row_panel("Error Analysis", {"h": 1, "w": 24, "x": 0, "y": y}, pid))
pid += 1; y += 1

# Root Errors + Cascading Failures stats
panels.append(stat_panel("Root Errors", [
    {"$match": {**_base_match(), "status": "failed", "error.name": {"$ne": "ChildWorkflowFailure"}}},
    {"$group": {"_id": None, "count": {"$sum": 1}}},
    {"$project": {"value": "$count", "_id": 0}}
], {"h": 5, "w": 6, "x": 0, "y": y}, pid,
    thresholds=[{"color": "green", "value": 0}, {"color": "orange", "value": 10}, {"color": "red", "value": 50}]))
pid += 1

panels.append(stat_panel("Cascading Failures (ChildWorkflowFailure)", [
    {"$match": {**_base_match(), "status": "failed", "error.name": "ChildWorkflowFailure"}},
    {"$group": {"_id": None, "count": {"$sum": 1}}},
    {"$project": {"value": "$count", "_id": 0}}
], {"h": 5, "w": 6, "x": 6, "y": y}, pid,
    thresholds=[{"color": "green", "value": 0}, {"color": "yellow", "value": 10}]))
pid += 1

# Root Errors Over Time (mini timeseries)
panels.append(timeseries_panel("Root Errors Over Time", [
    {"$match": {**_base_match(), "status": "failed", "error.name": {"$ne": "ChildWorkflowFailure"}}},
    {"$group": {"_id": {"$dateTrunc": {"date": "$createdAt", "unit": "hour"}}, "count": {"$sum": 1}}},
    {"$sort": {"_id": 1}},
    {"$project": {"time": "$_id", "value": "$count", "_id": 0}}
], {"h": 5, "w": 12, "x": 12, "y": y}, pid,
    overrides=[{"matcher": {"id": "byName", "options": "value"}, "properties": [{"id": "color", "value": {"fixedColor": "red", "mode": "fixed"}}, {"id": "displayName", "value": "Root Errors"}]}]))
pid += 1; y += 5

# Top Root Causes (bar chart) + Failed Activities (pie chart)
panels.append(barchart_panel("Top 10 Root Causes", [
    {"$match": {**_base_match(), "status": "failed", "error.name": {"$ne": "ChildWorkflowFailure"}}},
    {"$group": {"_id": {"$substrBytes": [{"$ifNull": ["$error.rootCauseMessage", "Unknown"]}, 0, 100]}, "count": {"$sum": 1}}},
    {"$sort": {"count": -1}},
    {"$limit": 10},
    {"$project": {"Cause": "$_id", "Count": "$count", "_id": 0}}
], {"h": 12, "w": 12, "x": 0, "y": y}, pid, x_field="Cause"))
pid += 1

panels.append(pie_panel("Failures by Activity", [
    {"$match": {**_base_match(), "status": "failed", "error.name": {"$ne": "ChildWorkflowFailure"}}},
    {"$group": {"_id": {"$ifNull": ["$error.failedActivity.name", "Unknown"]}, "count": {"$sum": 1}}},
    {"$sort": {"count": -1}},
    {"$limit": 15},
    {"$project": {"activity": "$_id", "value": "$count", "_id": 0}}
], {"h": 12, "w": 12, "x": 12, "y": y}, pid))
pid += 1; y += 12

# ─── Jobs by Artifact Type Row ───

panels.append(row_panel("Jobs by Artifact Type", {"h": 1, "w": 24, "x": 0, "y": y}, pid))
pid += 1; y += 1

# All Jobs by Artifact Type (piechart)
panels.append(pie_panel("All Jobs by Artifact Type", [
    {"$match": {**_base_match()}},
    {"$group": {"_id": "$artifactTypeId", "count": {"$sum": 1}}},
    {"$sort": {"count": -1}},
    {"$limit": 15},
    {"$project": {"artifactType": _artifact_name_switch("$_id"), "value": "$count", "_id": 0}}
], {"h": 12, "w": 12, "x": 0, "y": y}, pid))
pid += 1

# Failures by Artifact Type (piechart)
panels.append(pie_panel("Failures by Artifact Type", [
    {"$match": {**_base_match(), "status": "failed"}},
    {"$group": {"_id": "$artifactTypeId", "count": {"$sum": 1}}},
    {"$sort": {"count": -1}},
    {"$limit": 15},
    {"$project": {"artifactType": _artifact_name_switch("$_id"), "value": "$count", "_id": 0}}
], {"h": 12, "w": 12, "x": 12, "y": y}, pid))
pid += 1; y += 12

# Jobs Trend by Artifact Type (timeseries)
panels.append(timeseries_panel("Jobs Trend by Artifact Type", [
    {"$match": {**_base_match()}},
    {"$group": {"_id": {"time": {"$dateTrunc": {"date": "$createdAt", "unit": "hour"}}, "artifactTypeId": "$artifactTypeId"}, "count": {"$sum": 1}}},
    {"$sort": {"_id.time": 1}},
    {"$project": {"time": "$_id.time", "artifactTypeName": _artifact_name_switch("$_id.artifactTypeId"), "value": "$count", "_id": 0}}
], {"h": 12, "w": 24, "x": 0, "y": y}, pid,
    legend_placement="right",
    overrides=[{"matcher": {"id": "byRegexp", "options": "/^value /"}, "properties": [{"id": "displayName", "value": "${__field.labels.artifactTypeName}"}]}]))
pid += 1; y += 12

# ─── Artifact Types Table ───

panels.append(table_panel("Artifact Types Breakdown", [
    {"$match": {**_base_match()}},
    {"$group": {"_id": {"artifactTypeId": "$artifactTypeId", "status": "$status"}, "count": {"$sum": 1}}},
    {"$group": {
        "_id": "$_id.artifactTypeId",
        "total": {"$sum": "$count"},
        "completed": {"$sum": {"$cond": [{"$eq": ["$_id.status", "completed"]}, "$count", 0]}},
        "failed": {"$sum": {"$cond": [{"$eq": ["$_id.status", "failed"]}, "$count", 0]}},
        "running": {"$sum": {"$cond": [{"$eq": ["$_id.status", "running"]}, "$count", 0]}}
    }},
    {"$sort": {"total": -1}},
    {"$limit": 20},
    {"$project": {
        "Artifact Type": _artifact_name_switch("$_id"),
        "Total Jobs": "$total",
        "Completed": "$completed",
        "Failed": "$failed",
        "Running": "$running",
        "Failure Rate %": {"$round": [{"$cond": [{"$gt": ["$total", 0]}, {"$multiply": [{"$divide": ["$failed", "$total"]}, 100]}, 0]}, 1]},
        "_id": 0
    }}
], {"h": 10, "w": 24, "x": 0, "y": y}, pid,
    overrides=[
        {"matcher": {"id": "byName", "options": "Failure Rate %"}, "properties": [
            {"id": "custom.cellOptions", "value": {"mode": "gradient", "type": "gauge"}},
            {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "green", "value": 0}, {"color": "orange", "value": 5}, {"color": "red", "value": 20}]}},
            {"id": "max", "value": 100}
        ]},
        {"matcher": {"id": "byName", "options": "Failed"}, "properties": [{"id": "custom.cellOptions", "value": {"type": "color-text"}}, {"id": "color", "value": {"fixedColor": "red", "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "Completed"}, "properties": [{"id": "custom.cellOptions", "value": {"type": "color-text"}}, {"id": "color", "value": {"fixedColor": "green", "mode": "fixed"}}]}
    ],
    transformations=[{"id": "organize", "options": {
        "excludeByName": {},
        "indexByName": {"Artifact Type": 0, "Total Jobs": 1, "Completed": 2, "Failed": 3, "Running": 4, "Failure Rate %": 5},
        "renameByName": {}
    }}]))
pid += 1; y += 10

# ─── Avg Pending Time by Artifact Type ───

panels.append(row_panel("Performance", {"h": 1, "w": 24, "x": 0, "y": y}, pid))
pid += 1; y += 1

panels.append(barchart_panel("Avg Pending Time by Artifact Type (seconds)", [
    {"$match": {**_base_match(), "startTime": {"$exists": True}}},
    {"$project": {"artifactTypeId": 1, "pendingMs": {"$subtract": ["$startTime", "$createdAt"]}}},
    {"$match": {"pendingMs": {"$gt": 0}}},
    {"$group": {"_id": "$artifactTypeId",
                "avgPending": {"$avg": "$pendingMs"},
                "maxPending": {"$max": "$pendingMs"},
                "count": {"$sum": 1}}},
    {"$sort": {"avgPending": -1}},
    {"$limit": 15},
    {"$project": {
        "Artifact Type": _artifact_name_switch("$_id"),
        "Avg Pending (s)": {"$round": [{"$divide": ["$avgPending", 1000]}, 1]},
        "Max Pending (s)": {"$round": [{"$divide": ["$maxPending", 1000]}, 1]},
        "Jobs": "$count",
        "_id": 0
    }}
], {"h": 12, "w": 24, "x": 0, "y": y}, pid, x_field="Artifact Type"))
pid += 1; y += 12

# Avg Duration by Artifact Type
panels.append(barchart_panel("Avg Duration by Artifact Type (minutes)", [
    {"$match": {**_base_match(), "execution.totalDuration": {"$exists": True, "$gt": 0}}},
    {"$group": {"_id": "$artifactTypeId",
                "avgDuration": {"$avg": "$execution.totalDuration"},
                "count": {"$sum": 1}}},
    {"$sort": {"avgDuration": -1}},
    {"$limit": 15},
    {"$project": {
        "Artifact Type": _artifact_name_switch("$_id"),
        "Avg Duration (min)": {"$round": [{"$divide": ["$avgDuration", 60]}, 1]},
        "Jobs": "$count",
        "_id": 0
    }}
], {"h": 12, "w": 24, "x": 0, "y": y}, pid, x_field="Artifact Type"))
pid += 1; y += 12

# ─── Recent Jobs Table ───

panels.append(row_panel("Recent Jobs", {"h": 1, "w": 24, "x": 0, "y": y}, pid))
pid += 1; y += 1

# Root errors only (excludes ChildWorkflowFailure cascading errors)
panels.append(table_panel("Failed Jobs - Root Errors (export via Inspect → Data → Download)", [
    {"$match": {**_base_match(), "status": "failed", "error.name": {"$ne": "ChildWorkflowFailure"}}},
    {"$sort": {"createdAt": -1}},
    {"$limit": 500},
    {"$project": {
        "createdAt": 1,
        "Job ID": {"$toString": "$_id"},
        "Artifact Type": _artifact_name_switch("$artifactTypeId"),
        "Error Name": {"$ifNull": ["$error.name", "Unknown"]},
        "Root Cause": {"$substrBytes": [{"$ifNull": ["$error.rootCauseMessage", "Unknown"]}, 0, 200]},
        "Failed Activity": {"$ifNull": ["$error.failedActivity.name", ""]},
        "_id": 0
    }}
], {"h": 15, "w": 24, "x": 0, "y": y}, pid,
    overrides=[
        {"matcher": {"id": "byName", "options": "Root Cause"}, "properties": [{"id": "custom.width", "value": 450}, {"id": "custom.wrapText", "value": True}]},
        {"matcher": {"id": "byName", "options": "Artifact Type"}, "properties": [{"id": "custom.width", "value": 180}]},
        {"matcher": {"id": "byName", "options": "Error Name"}, "properties": [{"id": "custom.width", "value": 180}]},
        {"matcher": {"id": "byName", "options": "Failed Activity"}, "properties": [{"id": "custom.width", "value": 180}]},
        {"matcher": {"id": "byName", "options": "Job ID"}, "properties": [{"id": "custom.width", "value": 220}]}
    ],
    transformations=[{"id": "organize", "options": {
        "excludeByName": {},
        "indexByName": {"createdAt": 0, "Artifact Type": 1, "Error Name": 2, "Root Cause": 3, "Failed Activity": 4, "Job ID": 5},
        "renameByName": {"createdAt": "Created At"}
    }}]))
pid += 1; y += 15

# All failed jobs including cascading errors
panels.append(table_panel("Failed Jobs - All (including cascading errors)", [
    {"$match": {**_base_match(), "status": "failed"}},
    {"$sort": {"createdAt": -1}},
    {"$limit": 500},
    {"$project": {
        "createdAt": 1,
        "Job ID": {"$toString": "$_id"},
        "Artifact Type": _artifact_name_switch("$artifactTypeId"),
        "Error Name": {"$ifNull": ["$error.name", "Unknown"]},
        "Root Cause": {"$substrBytes": [{"$ifNull": ["$error.rootCauseMessage", "Unknown"]}, 0, 200]},
        "Failed Activity": {"$ifNull": ["$error.failedActivity.name", ""]},
        "Is Cascade": {"$cond": [{"$eq": ["$error.name", "ChildWorkflowFailure"]}, "Yes", "No"]},
        "_id": 0
    }}
], {"h": 15, "w": 24, "x": 0, "y": y}, pid,
    overrides=[
        {"matcher": {"id": "byName", "options": "Root Cause"}, "properties": [{"id": "custom.width", "value": 400}, {"id": "custom.wrapText", "value": True}]},
        {"matcher": {"id": "byName", "options": "Artifact Type"}, "properties": [{"id": "custom.width", "value": 180}]},
        {"matcher": {"id": "byName", "options": "Error Name"}, "properties": [{"id": "custom.width", "value": 180}]},
        {"matcher": {"id": "byName", "options": "Job ID"}, "properties": [{"id": "custom.width", "value": 220}]},
        {"matcher": {"id": "byName", "options": "Is Cascade"}, "properties": [{"id": "custom.width", "value": 90}]}
    ],
    transformations=[{"id": "organize", "options": {
        "excludeByName": {},
        "indexByName": {"createdAt": 0, "Artifact Type": 1, "Error Name": 2, "Root Cause": 3, "Failed Activity": 4, "Is Cascade": 5, "Job ID": 6},
        "renameByName": {"createdAt": "Created At"}
    }}]))
pid += 1; y += 15

panels.append(table_panel("Recent Jobs (All Statuses)", [
    {"$match": {**_base_match()}},
    {"$sort": {"createdAt": -1}},
    {"$limit": 50},
    {"$project": {
        "createdAt": 1,
        "Job ID": {"$toString": "$_id"},
        "Artifact Type": _artifact_name_switch("$artifactTypeId"),
        "Status": "$status",
        "Error": {"$cond": [
            {"$eq": ["$status", "failed"]},
            {"$substrBytes": [{"$ifNull": ["$error.rootCauseMessage", "No message"]}, 0, 80]},
            ""
        ]},
        "_id": 0
    }}
], {"h": 15, "w": 24, "x": 0, "y": y}, pid,
    overrides=[
        {"matcher": {"id": "byName", "options": "Error"}, "properties": [{"id": "custom.width", "value": 400}, {"id": "custom.wrapText", "value": True}]},
        {"matcher": {"id": "byName", "options": "Artifact Type"}, "properties": [{"id": "custom.width", "value": 200}]},
        {"matcher": {"id": "byName", "options": "Status"}, "properties": [{"id": "custom.width", "value": 90}]},
        {"matcher": {"id": "byName", "options": "Job ID"}, "properties": [{"id": "custom.width", "value": 220}]}
    ],
    transformations=[{"id": "organize", "options": {
        "excludeByName": {},
        "indexByName": {"createdAt": 0, "Artifact Type": 1, "Status": 2, "Job ID": 3, "Error": 4},
        "renameByName": {"createdAt": "Created At"}
    }}]))


# ── Assemble dashboard ──

dashboard = {
    "annotations": {
        "list": [{
            "builtIn": 1,
            "datasource": {"type": "grafana", "uid": "-- Grafana --"},
            "enable": True, "hide": True,
            "iconColor": "rgba(0, 211, 255, 1)",
            "name": "Annotations & Alerts", "type": "dashboard"
        }]
    },
    "editable": True,
    "fiscalYearStartMonth": 0,
    "graphTooltip": 1,
    "links": [],
    "panels": panels,
    "preload": False,
    "refresh": "30s",
    "schemaVersion": 42,
    "tags": ["artifacts", "eko", "mongodb", "monitoring"],
    "templating": {"list": [_build_artifact_type_variable()]},
    "time": {"from": "now-24h", "to": "now"},
    "timepicker": {},
    "timezone": "browser",
    "title": "Artifact Jobs Monitoring",
    "uid": "artifact-jobs-monitoring",
    "version": 1,
    "weekStart": ""
}

output_path = os.path.join(os.path.dirname(__file__), "artifact_jobs_grafana_dashboard.json")
with open(output_path, "w") as f:
    json.dump(dashboard, f, indent=2)

print(f"Dashboard written to {output_path}")
print(f"Total panels: {len(panels)}")
