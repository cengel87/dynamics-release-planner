# 🚀 Dynamics 365 & Power Platform Release Tracker

A comprehensive Streamlit dashboard for analyzing Microsoft Dynamics 365 and Power Platform release plans with advanced analytics and insights.

## 🚀 Quick Start

### Run Locally

1. **Install Python 3.8+** (if not already installed)

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the dashboard:**
   ```bash
   python -m streamlit run app.py
   ```
   
   Alternative commands:
   ```bash
   # If you renamed the file
   python -m streamlit run release-planner.py
   
   # Direct streamlit command (if in PATH)
   streamlit run app.py
   ```

4. **Open in browser:**
   - The dashboard will automatically open at `http://localhost:8501`
   - If not, navigate to the URL shown in the terminal

### Deploy to Streamlit Cloud

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for detailed deployment instructions to Streamlit Cloud.

### Requirements

The dashboard requires these Python packages (see `requirements.txt`):
- `streamlit` - Web framework
- `pandas` - Data processing
- `plotly` - Interactive charts
- `requests` - HTTP requests
- `beautifulsoup4` - HTML parsing

---

## ✨ Key Enhancements

### **New Features**

1. **GA Status Tracking** ⭐ NEW!
   - Identifies features that have reached General Availability
   - Based ONLY on Microsoft's published GA status and dates
   - Clear distinction between GA and pre-GA features
   - No assumptions about wave-based deployment
   - Important: GA status ≠ guaranteed production availability in your environment

2. **Google Search Integration** ⭐ NEW!
   - Every feature has a Google search link
   - Automatically searches: "[Feature Name] [Product] microsoft dynamics"
   - Quick access to documentation, blog posts, and community discussions
   - More useful than direct release plan links

3. **Executive Overview Tab**
   - Release momentum trends over time
   - Upcoming releases for next 90 days
   - Month-by-month release planning
   - Interactive trend visualization

4. **Release Wave Analysis**
   - Wave performance metrics (completion rates, preview duration)
   - Wave comparison charts
   - Deep-dive analysis for specific waves
   - Product breakdown by wave

5. **Product Breakdown Tab**
   - Product velocity matrix showing completion vs. activity
   - Recent update tracking (30-day window)
   - Side-by-side product comparison
   - Performance benchmarking

6. **Enhanced Filtering**
   - Date range filtering for GA releases
   - Multi-select filters with better UX
   - Keyword search across all fields
   - Filter persistence and state management

7. **Improved Analytics**
   - Days to/from GA calculations
   - Average preview duration metrics
   - Completion rate tracking
   - Activity heat mapping

8. **Better Visualizations**
   - Interactive Plotly charts
   - Timeline with better grouping options
   - Scatter plots for velocity analysis
   - Multi-panel comparison views

### **Bug Fixes & Improvements**

1. **Data Parsing**
   - More robust JSON parsing with error handling
   - Better handling of malformed data
   - Silent error skipping for individual features
   - Validation of parsed data quality

2. **Date Handling**
   - Fixed date parsing edge cases
   - Proper handling of TBD/N/A values
   - Timezone-aware calculations
   - Null-safe date operations

3. **Performance**
   - Optimized filtering operations
   - Better caching strategies
   - Reduced redundant calculations
   - Improved data aggregation

4. **UX Improvements**
   - Better empty state handling
   - Clearer metric labels
   - Responsive layout
   - Enhanced color coding
   - Informative tooltips and help text

5. **Data Quality**
   - Wave data cleaning (TBD handling)
   - Duplicate removal
   - Consistent data types
   - Better null handling

## 📊 Dashboard Tabs

### 1. Executive Overview
- **Purpose**: High-level strategic view for leadership
- **Metrics**: Release trends, upcoming milestones, status distribution
- **Use Case**: Monthly executive reviews, planning sessions

### 2. GA Status ⭐ NEW!
- **Purpose**: Track features that have reached General Availability
- **Metrics**: GA counts, timeline, wave-based tracking
- **Use Case**: Understanding Microsoft's GA declarations
- **Key Logic**: Features marked "GA" when:
  - Status = "Generally Available" AND
  - GA date has passed
- **Important**: GA status is based on Microsoft's release plans, not actual deployment verification

### 3. Release Information ⭐ NEW!
- **Purpose**: Understand how Microsoft releases work
- **Content**: 
  - Release wave schedule (Wave 1 & 2 timelines)
  - Release channels (Monthly vs Semi-Annual)
  - Feature availability types
  - GA vs deployment clarification
  - Best practices for planning
- **Source**: Official Microsoft Learn documentation
- **Use Case**: Understanding release process, planning change management

### 4. Release Wave Analysis
- **Purpose**: Track wave-specific performance
- **Metrics**: Completion rates, feature counts, preview duration
- **Use Case**: Wave planning, capacity assessment, timeline reviews

### 5. Product Breakdown
- **Purpose**: Compare product team performance
- **Metrics**: Velocity, completion %, recent activity
- **Use Case**: Team benchmarking, resource allocation

### 6. Timeline View
- **Purpose**: Visualize release schedules
- **Metrics**: Gantt-style timeline with flexible grouping
- **Use Case**: Release planning, dependency identification

### 7. Features Table
- **Purpose**: Detailed feature exploration
- **Metrics**: All feature attributes with sorting and filtering
- **Use Case**: Deep-dive analysis, stakeholder queries

### 8. Recent Updates
- **Purpose**: Track recent changes and activity
- **Metrics**: Updates by product over configurable time periods
- **Use Case**: Daily standup, weekly reviews, change tracking

## 🚀 Installation & Setup

### Prerequisites
- Python 3.8 or higher
- pip package manager

### Quick Start

1. **Clone or download the files**
   ```bash
   # Download the enhanced tracker
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the dashboard**
   ```bash
   streamlit run d365_release_tracker_enhanced.py
   ```

4. **Access the dashboard**
   - Open your browser to `http://localhost:8501`
   - The dashboard will automatically fetch the latest data

## 📖 Usage Guide

### Filtering Data

**Sidebar Filters:**
- **Search**: Quick keyword search at top of sidebar (searches across all fields)
- **Product**: Filter by specific Dynamics 365 or Power Platform products
- **Status**: Filter by lifecycle stage (Planned, Early Access, Preview, GA)
- **Release Wave**: Filter by Microsoft release wave
- **Investment Area**: Filter by functional area
- **GA Status**: Filter by "Reached GA" or "Not GA Yet"
- **Date Range**: Filter by GA date window

**Tips:**
- Leave filters empty to see all data
- Combine multiple filters for precise analysis
- Use date range for specific planning horizons

### Key Metrics Explained

**Days to GA**: 
- Positive = days until general availability
- Negative = days since GA release
- Helps prioritize upcoming releases

**Completion %**:
- Percentage of features that reached GA
- Indicates wave/product delivery performance
- Benchmark metric for planning

**GA Status** ⭐ NEW!:
- Count/percentage of features with GA status
- Based on Microsoft's published GA status and dates
- Does NOT guarantee actual availability in your environment
- Use as a planning reference, verify in your tenant

**Avg Preview Days**:
- Average time features spend in preview before GA
- Helps estimate release timelines
- Varies by product and complexity

### Export Options

**CSV Export**: 
- Click "Download CSV" to export filtered data
- Includes all columns for offline analysis
- Compatible with Excel and other tools

### Common Use Cases

**1. Planning Next Quarter's Features**
```
Filters: 
- Date Range: Next 90 days
- Status: Planned, Public Preview
Tab: Timeline View
```

**2. Executive Summary Report**
```
Filters: None (all data)
Tab: Executive Overview
Action: Screenshot trends and metrics
```

**3. Product Team Performance Review**
```
Filters: Select your products
Tab: Product Breakdown
Action: Compare completion % and velocity
```

**4. Wave Health Check**
```
Filters: Select specific wave
Tab: Release Wave Analysis
Action: Review completion % and delays
```

### **4. What Features Are Still Pre-GA?**
```
Filters: GA Status = "Not GA Yet"
Tab: GA Status → Not GA Yet section
Action: Review features in Preview, Early Access, or Planned status
```

## 🔧 Configuration

### Cache Settings
- Data refreshes every 4 hours automatically
- Manual refresh available via "↻ Refresh" button
- Adjust `ttl` in `@st.cache_data` decorator for different intervals

### Filtering
- All filters default to empty (shows all data)
- Select products, statuses, or other criteria to narrow results
- Use search box at top of sidebar for quick keyword filtering
- Filters persist during your session

### Display Limits
- Timeline view: Adjustable slider (10-100 items)
- Recent updates: Configurable periods (7-60 days)
- Modify in code for different defaults

### API Settings
- User-Agent header identifies the dashboard
- Timeout set to 90 seconds
- Update `HEADERS` dict for custom identification

## 🐛 Troubleshooting

**Issue**: "Only X features parsed — site format may have changed"
- **Cause**: Microsoft changed their API structure
- **Solution**: Check the URL and parsing regex patterns

**Issue**: Charts not displaying
- **Cause**: No data matches current filters
- **Solution**: Clear some filters or check date ranges

**Issue**: Slow loading
- **Cause**: Large dataset or slow network
- **Solution**: Data is cached; subsequent loads will be faster

**Issue**: Missing features
- **Cause**: Filters are too restrictive
- **Solution**: Clear all filters and verify data loaded

## 📈 Analytics Methodology

### Completion Rate Calculation
```
Completion % = (GA Features / Total Features) × 100
```

### Wave Performance
- Aggregates features by release wave identifier
- Tracks progression through lifecycle stages
- Calculates average duration in each stage

### Product Velocity
- Measures total features and completion rate
- Tracks recent activity (30-day window)
- Enables cross-product benchmarking

## 🔄 Data Update Frequency

- **Source**: Microsoft's public release plans API
- **Update**: Real-time from Microsoft (they update daily/weekly)
- **Cache**: Dashboard caches for 4 hours
- **Manual Refresh**: Available anytime via refresh button

## 💡 Tips & Best Practices

1. **Use date filters** for focused planning horizons
2. **Bookmark specific filter combinations** for recurring reports
3. **Export data regularly** for trend analysis over time
4. **Compare waves** to identify systematic delays or acceleration
5. **Monitor recent updates** daily to catch important changes
6. **Check upcoming releases** weekly for planning alignment

## 🤝 Support & Feedback

For issues or suggestions:
1. Check the troubleshooting section above
2. Verify you have the latest version
3. Review Microsoft's release plan site for data quality issues

## 📝 Version History

### v2.0 (Enhanced Version)
- Added Executive Overview tab
- Added Release Wave Analysis tab
- Added Product Breakdown tab
- Enhanced filtering with date ranges
- Improved analytics and metrics
- Better visualizations with Plotly
- Bug fixes in data parsing
- Performance optimizations

### v1.0 (Original Version)
- Basic feature listing
- Simple filtering
- Timeline view
- Status tracking

## 📄 License

This dashboard is a third-party tool that consumes Microsoft's public release plan data. 
It is not affiliated with or endorsed by Microsoft Corporation.

---

**Built with ❤️ using Streamlit**