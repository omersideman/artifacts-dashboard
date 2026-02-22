"""
Artifact Jobs Monitoring Dashboard
Real-time monitoring of job statuses, errors, and trends
"""

import streamlit as st
import pymongo
from bson import ObjectId
from datetime import datetime, timedelta, timezone
import pandas as pd
import plotly.express as px
from collections import defaultdict
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Load artifact type name mapping
_artifact_types_path = os.path.join(os.path.dirname(__file__), "artifactTypes.json")
with open(_artifact_types_path) as f:
    ARTIFACT_TYPE_NAMES = json.load(f)

def resolve_artifact_name(art_id):
    """Resolve an artifact type ObjectId to its friendly name, or full ID if not in JSON."""
    art_id_str = str(art_id)
    return ARTIFACT_TYPE_NAMES.get(art_id_str, art_id_str)

# Page config
st.set_page_config(
    page_title="Artifact Jobs Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .big-metric { font-size: 2.5rem; font-weight: bold; }
    .status-good { color: #00c853; }
    .status-warning { color: #ff6f00; }
    .status-critical { color: #d32f2f; }
</style>
""", unsafe_allow_html=True)

# Sidebar - Connection Settings
st.sidebar.title("Settings")

# MongoDB environment selector
MONGO_URIS = {
    "Production": os.getenv("MONGO_URI_PRODUCTION", ""),
    "Development": os.getenv("MONGO_URI_DEVELOPMENT", ""),
}

environment = st.sidebar.selectbox("Environment", list(MONGO_URIS.keys()))
mongo_uri = MONGO_URIS[environment]

if not mongo_uri:
    st.sidebar.error(f"⚠️ {environment} URI not set in .env file")

db_name = st.sidebar.text_input("Database Name", value="production-artifacts")
collection_name = "artifactJobs"

# Time range selector
time_range = st.sidebar.selectbox(
    "Time Range",
    ["Last Hour", "Last 6 Hours", "Last 24 Hours", "Last 7 Days", "Last 30 Days", "Custom"],
    index=2
)

if time_range == "Custom":
    col1, col2 = st.sidebar.columns(2)
    now_utc = datetime.now(timezone.utc)
    start_date = col1.date_input("Start Date", now_utc.date() - timedelta(days=7))
    end_date = col2.date_input("End Date", now_utc.date())
    start_datetime = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_datetime = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
else:
    time_ranges = {
        "Last Hour": 1/24,
        "Last 6 Hours": 6/24,
        "Last 24 Hours": 1,
        "Last 7 Days": 7,
        "Last 30 Days": 30
    }
    days_back = time_ranges[time_range]
    end_datetime = datetime.now(timezone.utc)
    start_datetime = end_datetime - timedelta(days=days_back)

# Artifact type filter
_type_options = ["All Types"] + list(ARTIFACT_TYPE_NAMES.values())
selected_type_name = st.sidebar.selectbox("Artifact Type", _type_options)

if selected_type_name == "All Types":
    _selected_type_ids = list(ARTIFACT_TYPE_NAMES.keys())
else:
    _selected_type_ids = [k for k, v in ARTIFACT_TYPE_NAMES.items() if v == selected_type_name]

selected_type_oids = [ObjectId(tid) for tid in _selected_type_ids]

# Auto-refresh
auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=False)
if auto_refresh:
    st.sidebar.info("Dashboard will refresh every 30 seconds")

# Connect button
connect_button = st.sidebar.button("🔌 Connect to MongoDB", type="primary")

# Initialize session state
if 'connected' not in st.session_state:
    st.session_state.connected = False
if 'client' not in st.session_state:
    st.session_state.client = None

# Connection logic
if connect_button or st.session_state.connected:
    try:
        if not st.session_state.connected or connect_button:
            with st.spinner("Connecting to MongoDB..."):
                client = pymongo.MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
                # Test connection
                client.server_info()
                st.session_state.client = client
                st.session_state.connected = True
                st.sidebar.success("✅ Connected!")
        
        client = st.session_state.client
        db = client[db_name]
        collection = db[collection_name]
        
        # Main dashboard
        st.title("Artifact Jobs Monitoring Dashboard")
        st.markdown(f"**Time Range:** {start_datetime.strftime('%Y-%m-%d %H:%M')} to {end_datetime.strftime('%Y-%m-%d %H:%M')}")
        
        # Shared match stage for all aggregations
        base_filter = {
            "createdAt": {"$gte": start_datetime, "$lte": end_datetime},
            "artifactTypeId": {"$in": selected_type_oids},
        }
        match_stage = {"$match": base_filter}
        
        # --- Aggregation: Status counts (metrics + pie chart) ---
        with st.spinner("Loading data..."):
            status_agg = list(collection.aggregate([
                match_stage,
                {"$group": {"_id": "$status", "count": {"$sum": 1}}}
            ]))
            
            status_counts = {doc["_id"] or "unknown": doc["count"] for doc in status_agg}
            total_jobs = sum(status_counts.values())
            
            if total_jobs == 0:
                st.warning("⚠️ No jobs found in this time range")
                st.stop()
            
            failed_count = status_counts.get("failed", 0)
            completed_count = status_counts.get("completed", 0)
            failure_rate = (failed_count / total_jobs * 100) if total_jobs > 0 else 0
            success_rate = (completed_count / total_jobs * 100) if total_jobs > 0 else 0
            
            st.success(f"✅ Found {total_jobs:,} jobs in range")
        
        # --- Aggregation: Avg duration (from execution.durations[0]) ---
        duration_agg = list(collection.aggregate([
            match_stage,
            {"$match": {
                "execution.durations": {"$exists": True, "$ne": []},
            }},
            {"$project": {"duration": {"$arrayElemAt": ["$execution.durations", 0]}}},
            {"$match": {"duration": {"$gt": 0}}},
            {"$group": {"_id": None, "avgDuration": {"$avg": "$duration"}, "count": {"$sum": 1}}}
        ]))
        avg_time = duration_agg[0]["avgDuration"] if duration_agg else 0
        avg_time = avg_time or 0
        
        # Metrics row
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Total Jobs", f"{total_jobs:,}")
        with col2:
            st.metric("Completed", f"{completed_count:,}")
        with col3:
            st.metric("Failed", f"{failed_count:,}")
        with col4:
            health_pct = 100 - failure_rate
            health_color = "green" if failure_rate < 5 else "orange" if failure_rate < 20 else "red"
            st.markdown(f"**Health**")
            st.markdown(f"<span style='font-size:2rem;font-weight:bold;color:{health_color}'>{health_pct:.0f}%</span>", unsafe_allow_html=True)
        with col5:
            if avg_time > 0:
                duration_label = f"{avg_time/60:.1f}m" if avg_time < 3600 else f"{avg_time/3600:.1f}h"
            else:
                duration_label = "N/A"
            st.metric("Avg Duration", duration_label)
        
        st.divider()
        
        # --- Aggregation: Timeline (jobs per hour by status) ---
        timeline_agg = list(collection.aggregate([
            match_stage,
            {"$group": {
                "_id": {
                    "hour": {"$dateTrunc": {"date": "$createdAt", "unit": "hour"}},
                    "status": "$status"
                },
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id.hour": 1}}
        ]))
        
        # Two column layout
        col_left, col_right = st.columns([2, 1])
        
        with col_left:
            st.subheader("Jobs Over Time")
            
            if timeline_agg:
                timeline_data = [{
                    "hour": doc["_id"]["hour"],
                    "status": doc["_id"]["status"] or "unknown",
                    "count": doc["count"]
                } for doc in timeline_agg]
                
                df_timeline = pd.DataFrame(timeline_data)
                
                fig_timeline = px.bar(
                    df_timeline,
                    x='hour',
                    y='count',
                    color='status',
                    title='Job Count by Hour',
                    color_discrete_map={'completed': '#00c853', 'failed': '#d32f2f', 'running': '#ff6f00'},
                    labels={'hour': 'Time', 'count': 'Number of Jobs'}
                )
                fig_timeline.update_layout(height=400)
                st.plotly_chart(fig_timeline, use_container_width=True)
        
        with col_right:
            st.subheader("Status Distribution")
            
            status_df = pd.DataFrame([
                {'Status': k, 'Count': v} for k, v in status_counts.items()
            ])
            
            fig_pie = px.pie(
                status_df,
                values='Count',
                names='Status',
                color='Status',
                color_discrete_map={'completed': '#00c853', 'failed': '#d32f2f', 'running': '#ff6f00'}
            )
            fig_pie.update_layout(height=400)
            st.plotly_chart(fig_pie, use_container_width=True)
        
        # --- Error Analysis (only if there are failures) ---
        if failed_count > 0:
            st.divider()
            st.subheader("Error Analysis")
            
            # Aggregation: error categorization (root vs cascade)
            error_cat_agg = list(collection.aggregate([
                match_stage,
                {"$match": {"status": "failed"}},
                {"$group": {
                    "_id": {"$cond": [
                        {"$eq": ["$error.name", "ChildWorkflowFailure"]},
                        "cascade",
                        "root"
                    ]},
                    "count": {"$sum": 1}
                }}
            ]))
            
            error_cats = {doc["_id"]: doc["count"] for doc in error_cat_agg}
            root_error_count = error_cats.get("root", 0)
            child_failure_count = error_cats.get("cascade", 0)
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Root Errors", root_error_count)
            with col2:
                st.metric("Cascading Failures", child_failure_count)
            
            col_err_left, col_err_right = st.columns(2)
            
            with col_err_left:
                st.subheader("Top Root Causes")
                
                # Aggregation: top root cause messages
                root_cause_agg = list(collection.aggregate([
                    match_stage,
                    {"$match": {"status": "failed", "error.name": {"$ne": "ChildWorkflowFailure"}}},
                    {"$group": {
                        "_id": {"$substrBytes": [
                            {"$ifNull": ["$error.rootCauseMessage", "Unknown"]},
                            0, 100
                        ]},
                        "count": {"$sum": 1}
                    }},
                    {"$sort": {"count": -1}},
                    {"$limit": 10}
                ]))
                
                if root_cause_agg:
                    cause_df = pd.DataFrame([{
                        "Cause": doc["_id"][:60] + "..." if len(doc["_id"]) > 60 else doc["_id"],
                        "Count": doc["count"]
                    } for doc in root_cause_agg])
                    
                    fig_causes = px.bar(
                        cause_df, x='Count', y='Cause', orientation='h',
                        title='Top 10 Error Causes'
                    )
                    fig_causes.update_layout(height=400)
                    st.plotly_chart(fig_causes, use_container_width=True)
            
            with col_err_right:
                st.subheader("Failed Activities")
                
                # Aggregation: failed activity names
                activity_agg = list(collection.aggregate([
                    match_stage,
                    {"$match": {"status": "failed", "error.name": {"$ne": "ChildWorkflowFailure"}}},
                    {"$group": {
                        "_id": {"$ifNull": ["$error.failedActivity.name", "Unknown"]},
                        "count": {"$sum": 1}
                    }},
                    {"$sort": {"count": -1}},
                    {"$limit": 15}
                ]))
                
                if activity_agg:
                    activity_df = pd.DataFrame([{
                        "Activity": doc["_id"],
                        "Count": doc["count"]
                    } for doc in activity_agg])
                    
                    fig_activities = px.pie(
                        activity_df, values='Count', names='Activity',
                        title='Failures by Activity'
                    )
                    fig_activities.update_layout(height=400)
                    st.plotly_chart(fig_activities, use_container_width=True)
            
            # Failures by Artifact Type (only when "All Types" selected)
            if selected_type_name == "All Types":
                st.divider()
                st.subheader("Failures by Artifact Type")
                
                # Aggregation: failed jobs by artifact type
                failed_by_type_agg = list(collection.aggregate([
                    match_stage,
                    {"$match": {"status": "failed"}},
                    {"$group": {
                        "_id": "$artifactTypeId",
                        "count": {"$sum": 1}
                    }},
                    {"$sort": {"count": -1}},
                    {"$limit": 15}
                ]))
                
                if failed_by_type_agg:
                    failed_type_data = [{
                        "Artifact Type": resolve_artifact_name(doc["_id"]),
                        "Failed Jobs": doc["count"]
                    } for doc in failed_by_type_agg]
                    
                    failed_type_df = pd.DataFrame(failed_type_data)
                    
                    fig_failed_types = px.pie(
                        failed_type_df,
                        values='Failed Jobs',
                        names='Artifact Type',
                        title=f'Distribution of {failed_count:,} Failed Jobs by Type'
                    )
                    fig_failed_types.update_layout(height=500)
                    st.plotly_chart(fig_failed_types, use_container_width=True)
        
        # --- Aggregation: Artifact type breakdown (only when "All Types" selected) ---
        if selected_type_name == "All Types":
            st.divider()
            st.subheader("Artifact Types")
            
            # Use time-only filter so we see all artifact types in data, not just those in JSON
            match_time_only = {"$match": {"createdAt": {"$gte": start_datetime, "$lte": end_datetime}}}
            artifact_agg = list(collection.aggregate([
                match_time_only,
                {"$group": {
                    "_id": {"artifactTypeId": "$artifactTypeId", "status": "$status"},
                    "count": {"$sum": 1}
                }}
            ]))
            
            artifact_types = defaultdict(lambda: {'total': 0, 'failed': 0, 'completed': 0})
            for doc in artifact_agg:
                art_id = str(doc["_id"]["artifactTypeId"])
                art_name = resolve_artifact_name(art_id)
                status = doc["_id"]["status"] or "unknown"
                count = doc["count"]
                artifact_types[art_name]['total'] += count
                if status == 'failed':
                    artifact_types[art_name]['failed'] += count
                elif status == 'completed':
                    artifact_types[art_name]['completed'] += count
            
            artifact_list = []
            for art_name, counts in artifact_types.items():
                fr = (counts['failed'] / counts['total'] * 100) if counts['total'] > 0 else 0
                artifact_list.append({
                    'Artifact Type': art_name,
                    'Total Jobs': counts['total'],
                    'Failed': counts['failed'],
                    'completed': counts['completed'],
                    'Failure Rate %': round(fr, 1)
                })
            
            artifact_df = pd.DataFrame(artifact_list).sort_values('Total Jobs', ascending=False)
            
            st.dataframe(artifact_df.head(15), use_container_width=True, hide_index=True)
                    
        # --- Recent Jobs Table (only fetch 50 documents) ---
        st.divider()
        st.subheader("Recent Jobs")
        
        recent_projection = {
            "status": 1, "createdAt": 1,
            "artifactTypeId": 1,
            "error.rootCauseMessage": 1,
        }
        recent_jobs = list(
            collection.find(
                base_filter,
                recent_projection
            ).sort("createdAt", -1).limit(50)
        )
        
        recent_list = []
        for job in recent_jobs:
            job_id_str = str(job.get('_id', ''))
            created = job.get('createdAt')
            created_str = str(created)[:19] if created else 'Unknown'
            status = job.get('status', 'unknown')
            artifact_type = resolve_artifact_name(job.get('artifactTypeId', ''))
            error_msg = ''
            if status == 'failed':
                error_msg = (job.get('error', {}) or {}).get('rootCauseMessage', 'No message')
                error_msg = error_msg[:60] if error_msg else 'No message'
            
            recent_list.append({
                'Job ID': job_id_str,
                'Created': created_str,
                'Artifact Type': artifact_type,
                'Status': status,
                'Error': error_msg
            })
        
        recent_df = pd.DataFrame(recent_list)
        st.dataframe(recent_df, use_container_width=True, hide_index=True)
        
        # Export section
        st.divider()
        col_export1, col_export2 = st.columns(2)
        
        with col_export1:
            export_projection = {
                "status": 1, "createdAt": 1,
                "artifactTypeId": 1, "error": 1,
            }
            if st.button("Export Failed Jobs (JSON)"):
                failed_cursor = collection.find(
                    {**base_filter, "status": "failed"},
                    export_projection
                ).sort("createdAt", -1).limit(5000)
                
                failed_export = json.dumps([{
                    '_id': str(job.get('_id', '')),
                    'createdAt': str(job.get('createdAt', '')),
                    'status': job.get('status'),
                    'error': json.loads(json.dumps(job.get('error', {}), default=str))
                } for job in failed_cursor], indent=2)
                
                st.download_button(
                    label="Download failed_jobs.json",
                    data=failed_export,
                    file_name=f"failed_jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
        
        with col_export2:
            st.info(f"Last updated: {datetime.now().strftime('%H:%M:%S')} | Total jobs in range: {total_jobs:,}")
        
        # Auto-refresh logic
        if auto_refresh:
            import time
            time.sleep(30)
            st.rerun()
        
    except pymongo.errors.ServerSelectionTimeoutError:
        st.sidebar.error("❌ Cannot connect to MongoDB. Check your URI and network connection.")
        st.session_state.connected = False
    except Exception as e:
        st.sidebar.error(f"❌ Error: {str(e)}")
        st.error(f"Error details: {str(e)}")
        st.session_state.connected = False

else:
    # Welcome screen
    st.title("Artifact Jobs Monitoring Dashboard")
    st.markdown("""
    ### Welcome! 👋
    
    This dashboard provides real-time monitoring of your artifact job processing system.
    
    **Features:**
    - Real-time job status tracking
    - Error analysis and categorization
    - Artifact type performance breakdown
    - Timeline visualization
    - Data export capabilities
    
    
    **Configuration:**
    - Adjust the time range to focus on specific periods
    - Enable auto-refresh for live monitoring
    - Filter by artifact type or error type
    """)
    
    st.info("👈 Configure your MongoDB connection in the sidebar to begin")
