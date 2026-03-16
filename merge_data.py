import pandas as pd
import os

# 1. Setup paths
folder = "datagovsg"

# 2. Load and Clean the Health Data
df_health = pd.read_csv(os.path.join(folder, 'AverageDailyPolyclinicAttendancesforSelectedDiseases.csv'))

# --- NEW: Filter for Respiratory infections ONLY ---
df_health = df_health[df_health['disease'] == 'Acute Upper Respiratory Tract infections'].copy()

# --- NEW: Convert 'epi_week' (2019-W01) into a real date ---
# This tells Python: "Take the first day (Monday) of that week"
df_health['date'] = pd.to_datetime(df_health['epi_week'] + '-1', format='%G-W%V-%u')

# 3. Load and Combine PM2.5 Data for Haze Years 
haze_years = ['2013', '2015', '2019']
pm25_list = []

for year in haze_years:
    file_name = f"Historical PM2.5 ({year}).csv"
    file_path = os.path.join(folder, file_name)
    if os.path.exists(file_path):
        temp_df = pd.read_csv(file_path)
        
        # Standardize the PM2.5 date column name to lowercase 'date'
        if 'Date' in temp_df.columns:
            temp_df.rename(columns={'Date': 'date'}, inplace=True)
            
        temp_df['date'] = pd.to_datetime(temp_df['date'])
        pm25_list.append(temp_df)

if not pm25_list:
    print("❌ Error: No PM2.5 files found! Check your filenames in the datagovsg folder.")
else:
    df_pm25 = pd.concat(pm25_list)

    # 4. Merge!
    # Now both dataframes have a 'date' column that matches
    master_df = pd.merge(df_health, df_pm25, on='date', how='inner')

    # 5. Save for AI Training
    master_df.to_csv('master_training_data.csv', index=False)
    print(f"✅ Success! Master Dataset created with {len(master_df)} rows.")
    print("You can now run 'python train_model.py'")