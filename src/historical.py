import numpy as np
import pandas as pd
from config.settings import ROOT

def load_history():
    p=ROOT/'data/historical/nyc_2024.csv'
    if not p.exists(): return pd.DataFrame()
    df=pd.read_csv(p,low_memory=False).drop_duplicates('collision_id')
    df['date']=pd.to_datetime(df['crash_date'],errors='coerce')
    df['hour']=pd.to_numeric(df['crash_time'].str.split(':').str[0],errors='coerce')
    df=df.dropna(subset=['date','hour']); df=df[df.hour.between(0,23)].copy()
    df['hour']=df.hour.astype(int); df['weekday']=df.date.dt.dayofweek; df['day']=df.date.dt.day_name()
    df['borough']=df['borough'].fillna('UNKNOWN')
    df['vehicle']=df['vehicle_type_code1'].fillna('Unknown').str.strip().str.upper()
    df['vehicle']=df.vehicle.where(df.vehicle.isin(df.vehicle.value_counts().head(12).index),'OTHER')
    for col in ['latitude','longitude','number_of_persons_injured','number_of_persons_killed']:
        df[col]=pd.to_numeric(df[col],errors='coerce')
    df['injury']=((df.number_of_persons_injured.fillna(0)>0)|(df.number_of_persons_killed.fillna(0)>0)).astype(int)
    df['severity']=np.select([df.number_of_persons_killed.fillna(0)>0,df.number_of_persons_injured.fillna(0)>0],['Fatal','Injury'],default='No injury reported')
    df['geo_valid']=df.latitude.between(40.45,40.95)&df.longitude.between(-74.3,-73.65)
    return df

def grid_hotspots(df):
    d=df[df.geo_valid].copy()
    if d.empty: return pd.DataFrame(columns=['latitude','longitude','crashes','injuries','score'])
    d['lat_grid']=np.floor(d.latitude*100)/100+.005; d['lon_grid']=np.floor(d.longitude*100)/100+.005
    g=d.groupby(['lat_grid','lon_grid']).agg(crashes=('collision_id','count'),injuries=('injury','sum')).reset_index()
    # Log normalization is transparent and avoids assigning 'critical' to most sparse cells.
    g['score']=100*np.log1p(g.crashes)/np.log1p(g.crashes.max())
    return g.rename(columns={'lat_grid':'latitude','lon_grid':'longitude'})

def historical_index(df,borough):
    counts=df[df.borough!='UNKNOWN'].groupby('borough').size()
    if borough not in counts or not len(counts): return None
    return round(float(counts[borough]/counts.max()*100),1)
