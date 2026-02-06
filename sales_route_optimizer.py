import streamlit as st
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans, DBSCAN
import folium
from folium import Marker, PolyLine
from streamlit_folium import folium_static
import io
from math import radians, sin, cos, sqrt, atan2

# Page configuration
st.set_page_config(page_title="Sales Route Optimizer", layout="wide", page_icon="🗺️")

# Custom CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #555;
        text-align: center;
        margin-bottom: 2rem;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">🗺️ Sales Route Optimizer</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Optimize daily visit clusters for sales personnel</div>', unsafe_allow_html=True)

# Helper Functions
def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate haversine distance between two points in km"""
    R = 6371  # Earth's radius in km
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return R * c

def find_lat_lng_columns(df):
    """Find latitude and longitude columns with flexible naming"""
    lat_col = None
    lng_col = None
    
    # Possible latitude column names
    lat_names = ['latitude', 'lat', 'Latitude', 'LAT', 'Lat']
    # Possible longitude column names
    lng_names = ['longitude', 'lng', 'long', 'lon', 'Longitude', 'LNG', 'LONG', 'LON', 'Long', 'Lng', 'Lon']
    
    for col in df.columns:
        if col in lat_names:
            lat_col = col
        if col in lng_names:
            lng_col = col
    
    return lat_col, lng_col

def nearest_neighbor_route(points, start_lat, start_lng):
    """
    Optimize route using nearest neighbor algorithm
    Returns ordered list of indices
    """
    if len(points) == 0:
        return []
    
    unvisited = list(range(len(points)))
    route = []
    current_lat, current_lng = start_lat, start_lng
    
    while unvisited:
        # Find nearest unvisited point
        min_dist = float('inf')
        nearest_idx = None
        
        for idx in unvisited:
            dist = haversine_distance(current_lat, current_lng, 
                                     points[idx]['lat'], points[idx]['lng'])
            if dist < min_dist:
                min_dist = dist
                nearest_idx = idx
        
        route.append(nearest_idx)
        unvisited.remove(nearest_idx)
        current_lat = points[nearest_idx]['lat']
        current_lng = points[nearest_idx]['lng']
    
    return route

def kmedoids_clustering(X, n_clusters, max_iter=300):
    """
    Simple K-Medoids implementation using PAM algorithm
    """
    n_samples = X.shape[0]
    
    # Initialize medoids randomly
    medoid_indices = np.random.choice(n_samples, n_clusters, replace=False)
    
    for iteration in range(max_iter):
        # Assign points to nearest medoid
        distances = np.zeros((n_samples, n_clusters))
        for i, medoid_idx in enumerate(medoid_indices):
            for j in range(n_samples):
                distances[j, i] = haversine_distance(
                    X[j, 0], X[j, 1], X[medoid_idx, 0], X[medoid_idx, 1]
                )
        
        labels = np.argmin(distances, axis=1)
        
        # Update medoids
        new_medoid_indices = []
        for cluster_id in range(n_clusters):
            cluster_points = np.where(labels == cluster_id)[0]
            if len(cluster_points) == 0:
                new_medoid_indices.append(medoid_indices[cluster_id])
                continue
            
            # Find point that minimizes total distance within cluster
            min_cost = float('inf')
            best_medoid = medoid_indices[cluster_id]
            
            for candidate in cluster_points:
                cost = sum(haversine_distance(X[candidate, 0], X[candidate, 1], 
                                             X[point, 0], X[point, 1]) 
                          for point in cluster_points)
                if cost < min_cost:
                    min_cost = cost
                    best_medoid = candidate
            
            new_medoid_indices.append(best_medoid)
        
        # Check for convergence
        if set(new_medoid_indices) == set(medoid_indices):
            break
        
        medoid_indices = new_medoid_indices
    
    return labels

def perform_clustering(df, lat_col, lng_col, n_clusters, algorithm='kmeans'):
    """Perform clustering on geographic data"""
    X = df[[lat_col, lng_col]].values
    
    if algorithm == 'kmeans':
        model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = model.fit_predict(X)
    elif algorithm == 'kmedoids':
        labels = kmedoids_clustering(X, n_clusters)
    elif algorithm == 'dbscan':
        # For DBSCAN, eps in radians (approx 0.01 rad ≈ 1.1 km)
        model = DBSCAN(eps=0.01, min_samples=5, metric='haversine')
        X_rad = np.radians(X)
        labels = model.fit_predict(X_rad)
    else:
        model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = model.fit_predict(X)
    
    return labels

def assign_clusters_to_salespersons(df, labels, num_salespersons, num_days, leads_per_day):
    """Assign clusters to salespersons and days"""
    df_copy = df.copy()
    df_copy['cluster'] = labels
    
    # Get unique clusters
    unique_clusters = df_copy['cluster'].unique()
    n_clusters = len(unique_clusters)
    
    # Create assignment structure
    assignments = []
    cluster_idx = 0
    
    for person in range(num_salespersons):
        for day in range(num_days):
            if cluster_idx < n_clusters:
                cluster_data = df_copy[df_copy['cluster'] == unique_clusters[cluster_idx]]
                
                # Limit to leads_per_day
                if len(cluster_data) > leads_per_day:
                    cluster_data = cluster_data.sample(n=leads_per_day, random_state=42)
                
                for idx, row in cluster_data.iterrows():
                    assignments.append({
                        'salesperson': f'Salesperson {person + 1}',
                        'day': f'Day {day + 1}',
                        'salesperson_id': person + 1,
                        'day_id': day + 1,
                        'original_index': idx,
                        **row.to_dict()
                    })
                
                cluster_idx += 1
    
    return pd.DataFrame(assignments)

def calculate_route_distance(route_data, office_lat, office_lng, lat_col, lng_col):
    """Calculate total route distance"""
    if len(route_data) == 0:
        return 0
    
    total_dist = 0
    current_lat, current_lng = office_lat, office_lng
    
    for _, row in route_data.iterrows():
        dist = haversine_distance(current_lat, current_lng, row[lat_col], row[lng_col])
        total_dist += dist
        current_lat, current_lng = row[lat_col], row[lng_col]
    
    # Return to office
    total_dist += haversine_distance(current_lat, current_lng, office_lat, office_lng)
    
    return total_dist

def create_numbered_icon(number):
    """Create a custom numbered icon HTML"""
    return folium.DivIcon(html=f"""
        <div style="
            background-color: #007bff;
            border: 2px solid white;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            color: white;
            font-size: 14px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.3);
        ">{number}</div>
    """)

def create_route_map(route_data, office_lat, office_lng, lat_col, lng_col, salesperson, day):
    """Create folium map with route visualization"""
    if len(route_data) == 0:
        m = folium.Map(location=[office_lat, office_lng], zoom_start=12)
        return m
    
    # Calculate center
    center_lat = route_data[lat_col].mean()
    center_lng = route_data[lng_col].mean()
    
    # Create map
    m = folium.Map(location=[center_lat, center_lng], zoom_start=12)
    
    # Add office marker
    folium.Marker(
        [office_lat, office_lng],
        popup="<b>Office</b><br>Start/End Point",
        tooltip="Office (Start/End)",
        icon=folium.Icon(color='red', icon='home', prefix='fa')
    ).add_to(m)
    
    # Add route markers with numbers
    route_coords = [[office_lat, office_lng]]
    
    for idx, row in route_data.iterrows():
        visit_order = row['visit_order']
        lat, lng = row[lat_col], row[lng_col]
        
        # Create popup with address info
        popup_text = f"""
        <b>Stop #{visit_order}</b><br>
        <b>Address:</b> {row.get('address', 'N/A')}<br>
        <b>City:</b> {row.get('city', 'N/A')}<br>
        <b>Zip:</b> {row.get('zip_code', 'N/A')}
        """
        
        # Add numbered marker
        folium.Marker(
            [lat, lng],
            popup=folium.Popup(popup_text, max_width=250),
            tooltip=f"Stop #{visit_order}",
            icon=create_numbered_icon(visit_order)
        ).add_to(m)
        
        route_coords.append([lat, lng])
    
    # Add return to office
    route_coords.append([office_lat, office_lng])
    
    # Draw route line
    folium.PolyLine(
        route_coords,
        color='#007bff',
        weight=4,
        opacity=0.8,
        popup=f"{salesperson} - {day}"
    ).add_to(m)
    
    return m

# Session state initialization
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None
if 'assignments' not in st.session_state:
    st.session_state.assignments = None

# Sidebar - File Upload and Parameters
with st.sidebar:
    st.header("📁 Data Upload")
    uploaded_file = st.file_uploader("Upload CSV or Excel file", type=['csv', 'xlsx'])
    
    st.header("⚙️ Parameters")
    
    num_salespersons = st.number_input("Number of Salespersons", min_value=1, max_value=50, value=5)
    num_days = st.number_input("Number of Working Days", min_value=1, max_value=30, value=5)
    leads_per_day = st.number_input("Leads per Salesperson per Day", min_value=1, max_value=100, value=20)
    
    algorithm = st.selectbox("Clustering Algorithm", ['kmeans', 'kmedoids', 'dbscan'])
    
    st.header("🏢 Office Location")
    office_lat = st.number_input("Office Latitude", value=40.7128, format="%.6f")
    office_lng = st.number_input("Office Longitude", value=-74.0060, format="%.6f")
    
    process_button = st.button("🚀 Generate Routes", type="primary", use_container_width=True)

# Main content area
if uploaded_file is not None:
    try:
        # Load data
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        st.success(f"✅ File uploaded successfully! {len(df)} records loaded.")
        
        # Find lat/lng columns
        lat_col, lng_col = find_lat_lng_columns(df)
        
        if lat_col is None or lng_col is None:
            st.error("❌ Could not find latitude/longitude columns. Please ensure your file has columns named 'latitude'/'longitude' or 'lat'/'long'.")
        else:
            st.info(f"📍 Found coordinates: {lat_col}, {lng_col}")
            
            # Show data preview
            with st.expander("📊 Data Preview"):
                st.dataframe(df.head(10))
            
            # Process data
            if process_button:
                with st.spinner("Processing... This may take a moment for large datasets."):
                    try:
                        # Calculate number of clusters
                        n_clusters = num_salespersons * num_days
                        
                        # Perform clustering
                        labels = perform_clustering(df, lat_col, lng_col, n_clusters, algorithm)
                        
                        # Assign clusters to salespersons and days
                        assignments = assign_clusters_to_salespersons(
                            df, labels, num_salespersons, num_days, leads_per_day
                        )
                        
                        # Store in session state
                        st.session_state.processed_data = df
                        st.session_state.assignments = assignments
                        st.session_state.lat_col = lat_col
                        st.session_state.lng_col = lng_col
                        st.session_state.office_lat = office_lat
                        st.session_state.office_lng = office_lng
                        
                        st.success("✅ Routes generated successfully!")
                        
                    except Exception as e:
                        st.error(f"❌ Error during processing: {str(e)}")
            
            # Display results if available
            if st.session_state.assignments is not None:
                assignments = st.session_state.assignments
                lat_col = st.session_state.lat_col
                lng_col = st.session_state.lng_col
                office_lat = st.session_state.office_lat
                office_lng = st.session_state.office_lng
                
                st.markdown("---")
                st.header("📋 Assignment Summary")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Assignments", len(assignments))
                with col2:
                    st.metric("Salespersons", assignments['salesperson'].nunique())
                with col3:
                    st.metric("Working Days", assignments['day'].nunique())
                
                # Route Visualization Section
                st.markdown("---")
                st.header("🗺️ Route Visualization")
                
                col1, col2 = st.columns(2)
                with col1:
                    selected_person = st.selectbox(
                        "Select Salesperson",
                        options=sorted(assignments['salesperson'].unique())
                    )
                with col2:
                    # Filter days for selected person
                    available_days = assignments[assignments['salesperson'] == selected_person]['day'].unique()
                    selected_day = st.selectbox(
                        "Select Day",
                        options=sorted(available_days)
                    )
                
                if selected_person and selected_day:
                    # Filter data for selected person and day
                    route_data = assignments[
                        (assignments['salesperson'] == selected_person) & 
                        (assignments['day'] == selected_day)
                    ].copy()
                    
                    if len(route_data) > 0:
                        # Prepare points for route optimization
                        points = [{'lat': row[lat_col], 'lng': row[lng_col]} for _, row in route_data.iterrows()]
                        
                        # Optimize route using nearest neighbor
                        route_order = nearest_neighbor_route(points, office_lat, office_lng)
                        
                        # Reorder data according to optimized route
                        route_data = route_data.iloc[route_order].reset_index(drop=True)
                        route_data['visit_order'] = range(1, len(route_data) + 1)
                        
                        # Calculate total distance
                        total_distance = calculate_route_distance(route_data, office_lat, office_lng, lat_col, lng_col)
                        
                        # Display metrics
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Stops", len(route_data))
                        with col2:
                            st.metric("Total Distance", f"{total_distance:.2f} km")
                        with col3:
                            st.metric("Avg Distance/Stop", f"{total_distance/len(route_data):.2f} km")
                        
                        # Create and display map
                        route_map = create_route_map(
                            route_data, office_lat, office_lng, 
                            lat_col, lng_col, selected_person, selected_day
                        )
                        folium_static(route_map, width=1200, height=600)
                        
                        # Display route details
                        st.subheader("📍 Route Details")
                        display_cols = ['visit_order', 'address', 'city', 'zip_code', lat_col, lng_col]
                        display_cols = [col for col in display_cols if col in route_data.columns]
                        st.dataframe(route_data[display_cols], use_container_width=True)
                        
                        # Download route data
                        csv = route_data.to_csv(index=False)
                        st.download_button(
                            label=f"📥 Download {selected_person} - {selected_day} Route",
                            data=csv,
                            file_name=f"{selected_person}_{selected_day}_route.csv",
                            mime="text/csv"
                        )
                    else:
                        st.warning("No assignments found for this selection.")
                
                # Download all assignments
                st.markdown("---")
                st.subheader("📥 Download All Assignments")
                csv_all = assignments.to_csv(index=False)
                st.download_button(
                    label="Download Complete Assignment Data",
                    data=csv_all,
                    file_name="all_assignments.csv",
                    mime="text/csv",
                    use_container_width=True
                )
    
    except Exception as e:
        st.error(f"❌ Error loading file: {str(e)}")
else:
    st.info("👈 Please upload a CSV or Excel file to get started.")
    
    # Show instructions
    st.markdown("""
    ### 📖 Instructions
    
    1. **Upload your data file** (CSV or Excel) containing lead information
    2. **Configure parameters** in the sidebar:
       - Number of salespersons
       - Number of working days
       - Leads to visit per day
       - Clustering algorithm
       - Office location (starting point)
    3. **Click "Generate Routes"** to process the data
    4. **Select a salesperson and day** to visualize the optimized route
    5. **Download** route data for implementation
    
    ### 📋 Required Columns
    Your file must contain:
    - **Latitude** (latitude, lat, LAT, etc.)
    - **Longitude** (longitude, lng, long, lon, etc.)
    - **Address** (optional but recommended)
    - **City, Zip Code** (optional)
    """)