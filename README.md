# Artifact Jobs Monitoring Dashboard 📊

A real-time Streamlit dashboard for monitoring your artifact job processing system.

## Features

- 📈 **Real-time Monitoring** - Live job status tracking with auto-refresh
- 🔍 **Error Analysis** - Categorized error breakdown with root cause analysis
- 🎯 **Artifact Type Insights** - Performance metrics by artifact type
- ⏱️ **Timeline Visualization** - Job trends over time
- 📥 **Data Export** - Export failed jobs or all jobs for further analysis
- 🎨 **Beautiful Visualizations** - Interactive charts and graphs

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Or install individually:
```bash
pip install streamlit pymongo pandas plotly
```

### 2. Run the Dashboard

```bash
streamlit run artifact_jobs_dashboard.py
```

The dashboard will open in your browser at `http://localhost:8501`

### 3. Connect to MongoDB

In the sidebar:
1. Enter your MongoDB URI (e.g., `mongodb://localhost:27017/`)
2. Enter your database name
3. Enter your collection name (e.g., `artifactJobs`)
4. Click "Connect to MongoDB"

## Usage

### Time Ranges
Select from preset ranges:
- Last Hour
- Last 6 Hours  
- Last 24 Hours
- Last 7 Days
- Last 30 Days
- Custom (pick specific dates)

### Auto-Refresh
Enable the "Auto-refresh (30s)" checkbox to automatically reload data every 30 seconds - perfect for live monitoring!

### Key Metrics

The dashboard shows:
- **Total Jobs** - Number of jobs in selected time range
- **Success Rate** - Percentage of successful jobs
- **Failure Rate** - Percentage of failed jobs
- **Health Status** - Overall system health (🟢/🟡/🔴)
- **Avg Duration** - Average job completion time

### Error Analysis

For failed jobs, you'll see:
- Root errors vs cascading failures
- Top error causes (with counts)
- Failed activities breakdown
- Artifact types with high failure rates

### Export Data

- **Export Failed Jobs** - Download failed jobs as JSON for detailed analysis
- **Export All Jobs** - Download all jobs as CSV for spreadsheet analysis

## Configuration

### MongoDB Connection Strings

**Local MongoDB:**
```
mongodb://localhost:27017/
```

**MongoDB Atlas:**
```
mongodb+srv://username:password@cluster.mongodb.net/
```

**With Authentication:**
```
mongodb://username:password@host:port/
```

### Security Note

Your MongoDB URI is stored only in your browser session and is not persisted. For production use, consider using environment variables:

```python
import os
mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
```

## Troubleshooting

### "Cannot connect to MongoDB"
- Check that MongoDB is running
- Verify the URI is correct
- Check network/firewall settings
- Ensure your IP is whitelisted (for Atlas)

### "No jobs found in this time range"
- Try expanding the time range
- Verify the collection name is correct
- Check that jobs exist in your database

### Dashboard is slow
- Reduce the time range
- The query limits to 10,000 jobs max
- Consider indexing the `createdAt` field in MongoDB

## Advanced Usage

### Running on a Server

To make the dashboard accessible from other machines:

```bash
streamlit run artifact_jobs_dashboard.py --server.address 0.0.0.0 --server.port 8501
```

### Custom Styling

Edit the CSS in the `st.markdown()` section at the top of the file to customize colors and styling.

### Adding Alerts

You can add custom alert logic by modifying the metrics sections. For example:

```python
if failure_rate > 20:
    st.error(f"⚠️ Alert: Failure rate is {failure_rate:.1f}%!")
```

## What It Monitors

This dashboard is designed to monitor the artifact job processing system and tracks:

1. **Job Statuses** - succeeded, failed, running
2. **Error Types** - ActivityFailure, ChildWorkflowFailure
3. **Root Causes** - Specific error messages and reasons
4. **Activities** - renderNexrenderJob, renderNexrenderMasterJob, etc.
5. **Artifact Types** - Performance by artifact type ID
6. **Timelines** - Job trends and patterns over time

## Tips

1. **Use Auto-Refresh** for live monitoring during incidents
2. **Export Failed Jobs** when you need to do deep analysis
3. **Check Artifact Types** to identify problematic templates
4. **Monitor Timeline** to spot patterns and trends
5. **Set Time Range to Last 7 Days** for weekly reviews

## Extending the Dashboard

Want to add more features? The code is easy to extend:

- Add new metrics in the metrics row
- Create new visualizations with Plotly
- Add filtering by artifact type or error type
- Implement alerts and notifications
- Connect to multiple collections

## Support

The dashboard is designed to work with the artifact job MongoDB schema that includes:
- `_id` - Job ID
- `status` - Job status
- `createdAt` - Creation timestamp
- `completedAt` - Completion timestamp (optional)
- `error` - Error details (for failed jobs)
  - `name` - Error type
  - `rootCauseMessage` - Root cause
  - `failedActivity.name` - Failed activity name
- `artifactTypeId` - Artifact type reference

Enjoy monitoring your jobs! 🚀
