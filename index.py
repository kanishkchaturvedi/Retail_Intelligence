import streamlit as st
import pandas as pd
import time
import os
import base64
from io import BytesIO
import json
from threading import Thread
import queue

# Import your existing scraping function
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import re
from fuzzywuzzy import fuzz

# Your existing search_amazon function
def search_amazon(product_name):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.74 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 10)

    try:
        driver.get("https://www.amazon.in/")
        search_box = wait.until(EC.presence_of_element_located((By.ID, "twotabsearchtextbox")))
        search_box.send_keys(product_name)
        search_box.send_keys(Keys.RETURN)
        time.sleep(3)

        products = wait.until(EC.presence_of_all_elements_located((By.XPATH, '//div[contains(@data-component-type, "s-search-result")]')))
        if not products:
            print("No products found.")
            return None
        
        best_match = None
        best_match_link = None
        highest_match_score = 0
        i = 0

        for product in products:
            try:
                is_sponsored = product.find_elements(By.XPATH, './/span[contains(text(), "Sponsored")]')
                if is_sponsored:
                    continue  
                
                title_element = product.find_element(By.XPATH, './/h2/span')
                title = title_element.text.strip()
                match_score = fuzz.partial_ratio(product_name.lower(), title.lower())
                if match_score > highest_match_score:
                    highest_match_score = match_score
                    best_match = title
                    product_link = product.find_element(By.XPATH, './/a[contains(@class, "a-link-normal")][@href]').get_attribute("href")
                    if product_link.startswith("/"):
                        product_link = "https://www.amazon.in" + product_link
                    best_match_link = product_link
                i += 1
                if i == 2:
                    break
            except:
                continue

        if best_match == None:
            print("No suitable match found.")
            return None

        driver.get(best_match_link)
        time.sleep(2)

        try:
            title = wait.until(EC.presence_of_element_located((By.ID, "productTitle"))).text.strip()
        except:
            title = "Title Not Found"

        try:
            price = driver.find_element(By.XPATH, './/span[contains(@class, "a-price-whole")]').text.strip()
        except:
            price = "Price Not Found"

        try:
            reviews = driver.find_element(By.XPATH, '//span[@id="acrCustomerReviewText"]').text
        except:
            reviews = "No Reviews"

        try:
            ranking = driver.find_element(By.XPATH, '//span[@id="acrPopover"]').get_attribute("title")
        except:
            ranking = "Ranking Not Available"

        related_products = []
        try:
            elements = driver.find_element(By.XPATH, '//div[contains(@id, "sp_detail_thematic-prime_theme_for_non_prime_members")]')
            competitors = elements.find_elements(By.XPATH, './/li[contains(@class, "a-carousel-card")]')

            for comp in competitors[:5]:
                try:
                    comp_title = comp.find_element(By.XPATH, './/div[contains(@class, "sponsored-products-truncator-afo-4")]').text.strip()
                except:
                    comp_title = "Title Not Available"
                
                try:
                    comp_price = comp.find_element(By.XPATH, './/span[@class="a-price-whole"]').text.strip()
                except:
                    comp_price = "Price Not Available"
                
                try:
                    comp_ranking_element = comp.find_element(By.XPATH, './/a[contains(@class, "adReviewLink")]').get_attribute("aria-label")
                    rating_match = re.search(r"(\d+\.\d+) out of (\d+) stars", comp_ranking_element)
                    comp_ranking = rating_match.group(0) if rating_match else "Rating Not Available"
                except:
                    comp_ranking = "Rating Not Available"
                
                try:
                    reviews_match = re.search(r"(\d+)\s+ratings?", comp_ranking_element)
                    comp_reviews = reviews_match.group(1) if reviews_match else "No Reviews"
                except:
                    comp_reviews = "No Reviews"
                
                related_products.append({
                    "Title": comp_title,
                    "Price": comp_price,
                    "Rating": comp_ranking,
                    "Reviews": comp_reviews
                })
        except:
            pass  # No related products found

        product_info = {
            "Title": title,
            "Price": price,
            "Reviews Count": reviews,
            "Ranking": ranking,
            "Product Link": best_match_link,
            "Related Products": related_products
        }

        return product_info
    
    except Exception as e:
        print(f"Error: {e}")
        return None
    finally:
        driver.quit()

# Function to process products in a queue for multithreading
def process_queue(q, results, progress_counter):
    while not q.empty():
        idx, product_name = q.get()
        try:
            results[idx] = search_amazon(product_name)
            progress_counter[0] += 1
        except Exception as e:
            results[idx] = {"Error": str(e)}
            progress_counter[0] += 1
        finally:
            q.task_done()

# Set up the Streamlit page
st.set_page_config(
    page_title="Retail Intelligence Dashboard",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS to make the UI more modern
st.markdown("""
<style>
    .main {
        background-color: #f8f9fa;
    }
    .stButton>button {
        background-color: #4CAF50;
        color: white;
        padding: 12px 20px;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-weight: bold;
        transition: background-color 0.3s;
    }
    .stButton>button:hover {
        background-color: #45a049;
    }
    .upload-box {
        border: 2px dashed #aaa;
        border-radius: 10px;
        padding: 30px;
        text-align: center;
        margin-bottom: 20px;
        background-color: white;
    }
    .product-card {
        background-color: white;
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    .competitor-card {
        background-color: #f1f1f1;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 10px;
    }
    .metric-container {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-bottom: 20px;
    }
    .metric-box {
        background-color: white;
        border-radius: 8px;
        padding: 15px;
        flex: 1;
        min-width: 120px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        text-align: center;
    }
    .metric-value {
        font-size: 24px;
        font-weight: bold;
        margin: 5px 0;
    }
    .metric-label {
        font-size: 14px;
        color: #666;
    }
    h1, h2, h3 {
        color: #333;
    }
    .header {
        padding: 20px;
        background-color: #4CAF50;
        border-radius: 10px;
        color: white;
        margin-bottom: 30px;
    }
    .stProgress > div > div {
        background-color: #4CAF50;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<div class="header"><h1>🛒 Retail Intelligence Dashboard</h1></div>', unsafe_allow_html=True)

# Initialize session state
if 'df' not in st.session_state:
    st.session_state.df = None
if 'results' not in st.session_state:
    st.session_state.results = {}
if 'analyzed' not in st.session_state:
    st.session_state.analyzed = False
if 'selected_product' not in st.session_state:
    st.session_state.selected_product = None
if 'progress' not in st.session_state:
    st.session_state.progress = 0
if 'total_products' not in st.session_state:
    st.session_state.total_products = 0

# Create tabs
tab1, tab2 = st.tabs(["📤 Upload & Process", "📊 Analysis Dashboard"])

with tab1:
    st.markdown("<h2>Upload Product Data</h2>", unsafe_allow_html=True)
    
    # File upload section
    with st.container():
        st.markdown('<div class="upload-box">', unsafe_allow_html=True)
        uploaded_file = st.file_uploader("Choose an Excel file containing product data", type=["xlsx", "xls"])
        st.markdown('</div>', unsafe_allow_html=True)
        
        if uploaded_file is not None:
            try:
                df = pd.read_excel(uploaded_file)
                required_columns = ["Brand", "Category", "Product Name", "Model Number"]
                if all(col in df.columns for col in required_columns):
                    st.session_state.df = df
                    st.success("✅ File uploaded successfully!")
                    
                    st.markdown("<h3>Preview of uploaded data</h3>", unsafe_allow_html=True)
                    st.dataframe(df.head(10), use_container_width=True)
                    
                    st.markdown("<h3>Products found in the Excel file</h3>", unsafe_allow_html=True)
                    products = df["Product Name"].tolist()
                    st.session_state.total_products = len(products)
                    
                    # Display products as tags in a container
                    cols = st.columns(3)
                    for i, product in enumerate(products):
                        cols[i % 3].markdown(f"<div style='background-color: #e1f5e1; padding: 8px; margin: 4px; border-radius: 5px;'>{product}</div>", unsafe_allow_html=True)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Analyze All Products"):
                            st.session_state.results = {}
                            st.session_state.progress = 0
                            
                            # Create a progress bar
                            progress_bar = st.progress(0)
                            status_text = st.empty()
                            
                            # Set up multithreading queue
                            q = queue.Queue()
                            for idx, product in enumerate(products):
                                q.put((idx, product))
                            
                            # Initialize results list and progress counter
                            results = [None] * len(products)
                            progress_counter = [0]  # Use list to make it mutable for threads
                            
                            # Create and start threads (use 3 threads max to avoid overloading)
                            num_threads = min(3, len(products))
                            threads = []
                            for _ in range(num_threads):
                                thread = Thread(target=process_queue, args=(q, results, progress_counter))
                                thread.daemon = True
                                thread.start()
                                threads.append(thread)
                            
                            # Update progress bar
                            while progress_counter[0] < len(products):
                                progress_percentage = progress_counter[0] / len(products)
                                progress_bar.progress(progress_percentage)
                                status_text.text(f"Processing {progress_counter[0]}/{len(products)} products...")
                                time.sleep(0.1)
                            
                            # Wait for all threads to complete
                            for thread in threads:
                                thread.join()
                            
                            # Finalize progress
                            progress_bar.progress(1.0)
                            status_text.text(f"Completed analyzing {len(products)} products!")
                            
                            # Store results in session state
                            for idx, result in enumerate(results):
                                if result:
                                    st.session_state.results[products[idx]] = result
                            
                            st.session_state.analyzed = True
                            st.session_state.progress = 100
                            
                            # Add a success message
                            st.success("✅ Analysis complete! Go to the Analysis Dashboard tab to view results.")
                    
                    with col2:
                        if st.button("Select Individual Product"):
                            st.session_state.selected_product = None
                            product_selection = st.selectbox("Choose a product to analyze:", products)
                            if st.button("Analyze Selected Product"):
                                with st.spinner(f"Analyzing {product_selection}..."):
                                    result = search_amazon(product_selection)
                                    if result:
                                        st.session_state.results[product_selection] = result
                                        st.session_state.selected_product = product_selection
                                        st.success(f"✅ Analysis complete for {product_selection}!")
                                        st.markdown("Go to the Analysis Dashboard tab to view results.")
                                    else:
                                        st.error("❌ Failed to retrieve data for this product.")
                else:
                    st.error("❌ The Excel file must contain columns for Brand, Category, Product Name, and Model Number.")
            except Exception as e:
                st.error(f"❌ Error processing file: {str(e)}")
    
    # Download template
    st.markdown("<h3>Don't have a file? Download a template:</h3>", unsafe_allow_html=True)
    
    # Create a template Excel file
    def create_template():
        df = pd.DataFrame({
            "Brand": ["Dyanora", "Dyanora"],
            "Category": ["Television", "Television"],
            "Product Name": ["Dyanora 24 INCH HD Ready LED TV (DY-LD24H0N)", "Dyanora 24 INCH HD Ready LED Smart Linux TV (DY-LD24H4S)"],
            "Model Number": ["DY-LD24H0N", "DY-LD24H4S"]
        })
        buffer = BytesIO()
        df.to_excel(buffer, index=False)
        buffer.seek(0)
        return buffer

    template = create_template()
    st.download_button(
        label="📥 Download Template Excel",
        data=template,
        file_name="retail_intelligence_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

with tab2:
    st.markdown("<h2>Retail Intelligence Analysis</h2>", unsafe_allow_html=True)
    
    if not st.session_state.results:
        st.info("📋 Please upload an Excel file and analyze products to see results here.")
    else:
        # Create a dropdown to select products for viewing
        available_products = list(st.session_state.results.keys())
        if available_products:
            selected = st.selectbox("Select a product to view details:", available_products)
            
            if selected and selected in st.session_state.results:
                product_data = st.session_state.results[selected]
                
                # Main product details
                st.markdown(f"<h3>Product Analysis: {selected}</h3>", unsafe_allow_html=True)
                
                # Extract dataframe metadata for this product if available
                product_metadata = {}
                if st.session_state.df is not None:
                    df = st.session_state.df
                    product_row = df[df["Product Name"] == selected]
                    if not product_row.empty:
                        product_metadata = product_row.iloc[0].to_dict()
                
                # Product details in a card
                st.markdown('<div class="product-card">', unsafe_allow_html=True)
                
                # Product metadata and Amazon data in columns
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("<h4>Product Information</h4>", unsafe_allow_html=True)
                    if product_metadata:
                        st.markdown(f"**Brand:** {product_metadata.get('Brand', 'N/A')}")
                        st.markdown(f"**Category:** {product_metadata.get('Category', 'N/A')}")
                        st.markdown(f"**Model Number:** {product_metadata.get('Model Number', 'N/A')}")
                
                with col2:
                    st.markdown("<h4>Amazon Data</h4>", unsafe_allow_html=True)
                    st.markdown(f"**Found Product Title:** {product_data.get('Title', 'N/A')}")
                    st.markdown(f"**Price:** ₹{product_data.get('Price', 'N/A')}")
                    st.markdown(f"**Reviews:** {product_data.get('Reviews Count', 'N/A')}")
                    st.markdown(f"**Rating:** {product_data.get('Ranking', 'N/A')}")
                    
                    # Product link as a button
                    if product_data.get('Product Link'):
                        st.markdown(f"[View on Amazon]({product_data['Product Link']})")
                
                st.markdown('</div>', unsafe_allow_html=True)
                
                # Competitive Analysis Section
                st.markdown("<h3>Competitive Analysis</h3>", unsafe_allow_html=True)
                
                related_products = product_data.get('Related Products', [])
                if related_products:
                    # Create metrics at the top
                    st.markdown('<div class="metric-container">', unsafe_allow_html=True)
                    
                    # Calculate average competitor price
                    competitor_prices = []
                    for prod in related_products:
                        try:
                            price = prod.get('Price', '0')
                            price = price.replace(',', '')  # Remove commas
                            competitor_prices.append(int(price))
                        except (ValueError, TypeError):
                            pass
                    
                    if competitor_prices:
                        avg_price = sum(competitor_prices) / len(competitor_prices)
                        
                        # Try to get the main product's price for comparison
                        try:
                            main_price = product_data.get('Price', '0').replace(',', '')
                            main_price = int(main_price)
                            price_diff = main_price - avg_price
                            price_diff_pct = (price_diff / avg_price) * 100 if avg_price > 0 else 0
                        except (ValueError, TypeError):
                            main_price = 0
                            price_diff = 0
                            price_diff_pct = 0
                        
                        # Display metrics
                        st.markdown(f'''
                        <div class="metric-box">
                            <div class="metric-label">Your Price</div>
                            <div class="metric-value">₹{main_price}</div>
                        </div>
                        <div class="metric-box">
                            <div class="metric-label">Avg. Competitor Price</div>
                            <div class="metric-value">₹{avg_price:.0f}</div>
                        </div>
                        <div class="metric-box">
                            <div class="metric-label">Price Difference</div>
                            <div class="metric-value" style="color: {'red' if price_diff > 0 else 'green'}">
                                {price_diff:.0f} ({price_diff_pct:.1f}%)
                            </div>
                        </div>
                        <div class="metric-box">
                            <div class="metric-label">Competitors Found</div>
                            <div class="metric-value">{len(related_products)}</div>
                        </div>
                        ''', unsafe_allow_html=True)
                    
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Competitor products as cards
                    for i, competitor in enumerate(related_products):
                        st.markdown(f'<div class="competitor-card">', unsafe_allow_html=True)
                        st.markdown(f"<h4>Competitor #{i+1}</h4>", unsafe_allow_html=True)
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"**Product:** {competitor.get('Title', 'N/A')}")
                            st.markdown(f"**Price:** ₹{competitor.get('Price', 'N/A')}")
                        
                        with col2:
                            st.markdown(f"**Rating:** {competitor.get('Rating', 'N/A')}")
                            st.markdown(f"**Reviews:** {competitor.get('Reviews', 'N/A')}")
                        
                        st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.info("No competitor products found for this item.")
                
                # Export options
                st.markdown("<h3>Export Analysis</h3>", unsafe_allow_html=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    # Export as JSON
                    json_data = json.dumps(product_data, indent=4)
                    st.download_button(
                        label="📥 Export as JSON",
                        data=json_data,
                        file_name=f"{selected.replace(' ', '_')}_analysis.json",
                        mime="application/json"
                    )
                
                with col2:
                    # Export as Excel
                    def create_excel_report(product_data, product_name):
                        # Create a DataFrame for the main product
                        main_df = pd.DataFrame({
                            "Product Name": [product_name],
                            "Title": [product_data.get('Title', 'N/A')],
                            "Price": [product_data.get('Price', 'N/A')],
                            "Reviews": [product_data.get('Reviews Count', 'N/A')],
                            "Rating": [product_data.get('Ranking', 'N/A')],
                            "Product Link": [product_data.get('Product Link', 'N/A')]
                        })
                        
                        # Create a DataFrame for competitors
                        competitors = product_data.get('Related Products', [])
                        comp_data = []
                        for i, comp in enumerate(competitors):
                            comp_data.append({
                                "Competitor #": i+1,
                                "Title": comp.get('Title', 'N/A'),
                                "Price": comp.get('Price', 'N/A'),
                                "Rating": comp.get('Rating', 'N/A'),
                                "Reviews": comp.get('Reviews', 'N/A')
                            })
                        
                        comp_df = pd.DataFrame(comp_data) if comp_data else pd.DataFrame()
                        
                        # Create Excel file with multiple sheets
                        buffer = BytesIO()
                        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                            main_df.to_excel(writer, sheet_name='Product Details', index=False)
                            if not comp_df.empty:
                                comp_df.to_excel(writer, sheet_name='Competitors', index=False)
                        
                        buffer.seek(0)
                        return buffer
                    
                    excel_data = create_excel_report(product_data, selected)
                    st.download_button(
                        label="📥 Export as Excel Report",
                        data=excel_data,
                        file_name=f"{selected.replace(' ', '_')}_report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
        
        # Batch export option for all products
        if len(available_products) > 1:
            st.markdown("<h3>Batch Export</h3>", unsafe_allow_html=True)
            
            if st.button("📥 Export All Products Data"):
                # Create Excel file with all product data
                buffer = BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    # Summary sheet
                    summary_data = []
                    for product_name, product_data in st.session_state.results.items():
                        summary_data.append({
                            "Product Name": product_name,
                            "Title on Amazon": product_data.get('Title', 'N/A'),
                            "Price": product_data.get('Price', 'N/A'),
                            "Reviews Count": product_data.get('Reviews Count', 'N/A'),
                            "Rating": product_data.get('Ranking', 'N/A'),
                            "Competitors Found": len(product_data.get('Related Products', []))
                        })
                    
                    pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
                    
                    # Individual product sheets
                    for product_name, product_data in st.session_state.results.items():
                        # Main product data
                        sheet_name = product_name[:31]  # Excel limits sheet names to 31 chars
                        product_df = pd.DataFrame({
                            "Parameter": ["Title", "Price", "Reviews", "Rating", "URL"],
                            "Value": [
                                product_data.get('Title', 'N/A'),
                                product_data.get('Price', 'N/A'),
                                product_data.get('Reviews Count', 'N/A'),
                                product_data.get('Ranking', 'N/A'),
                                product_data.get('Product Link', 'N/A')
                            ]
                        })
                        
                        # Competitor data
                        competitors = product_data.get('Related Products', [])
                        comp_data = []
                        for i, comp in enumerate(competitors):
                            comp_data.append({
                                "Competitor #": i+1,
                                "Title": comp.get('Title', 'N/A'),
                                "Price": comp.get('Price', 'N/A'),
                                "Rating": comp.get('Rating', 'N/A'),
                                "Reviews": comp.get('Reviews', 'N/A')
                            })
                        
                        comp_df = pd.DataFrame(comp_data) if comp_data else pd.DataFrame()
                        
                        # Write to Excel
                        product_df.to_excel(writer, sheet_name=sheet_name, startrow=0, index=False)
                        if not comp_df.empty:
                            comp_df.to_excel(writer, sheet_name=sheet_name, startrow=8, index=False)
                
                buffer.seek(0)
                st.download_button(
                    label="💾 Download Complete Analysis Report",
                    data=buffer,
                    file_name="retail_intelligence_full_report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# Footer
st.markdown("""
<div style="text-align: center; margin-top: 40px; padding: 20px; background-color: #f8f9fa; border-radius: 10px;">
    <p style="color: #666;">Retail Intelligence Dashboard © 2025</p>
</div>
""", unsafe_allow_html=True)
