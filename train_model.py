import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

# 1. LOAD THE RAW FILES
print("📂 Loading files...")
df_health = pd.read_csv('datagovsg/AverageDailyPolyclinicAttendancesforSelectedDiseases.csv')
df_pm25 = pd.read_csv('datagovsg/Historical PM2.5 (2019).csv')

# 2. FIX HEALTH DATA
# Filter for Respiratory cases
df_health = df_health[df_health['disease'] == 'Acute Upper Respiratory Tract infections'].copy()
# Convert epi_week to a real date (Monday of that week)
df_health['date'] = pd.to_datetime(df_health['epi_week'] + '-1', format='%G-W%V-%u')

# 3. FIX PM2.5 DATA
# Your file uses 'date' and 'pm25_one_hourly'
df_pm25['date'] = pd.to_datetime(df_pm25['date'])

# 4. AGGREGATE PM2.5 (Hourly to Daily)
# We take the average of 'pm25_one_hourly' for each day
df_pm25_daily = df_pm25.groupby('date')['pm25_one_hourly'].mean().reset_index()

# 5. MERGE
# Join the daily PM2.5 averages with the health data by date
master_df = pd.merge(df_health, df_pm25_daily, on='date', how='inner')

# 6. TRAIN & EVALUATE
if not master_df.empty:
    master_df = master_df.dropna()
    X = master_df[['pm25_one_hourly']] # Our "Cause"
    y = master_df['no._of_cases']      # Our "Effect"
    
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    # Predict and calculate error
    mae = mean_absolute_error(y, model.predict(X))
    
    print(f"\n✅ SUCCESS! Data points merged: {len(master_df)}")
    print(f"🚀 YOUR MAE SCORE IS: {mae:.2f}")
else:
    print("❌ No matching dates found between 2019 air data and health data.")