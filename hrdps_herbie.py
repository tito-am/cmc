from herbie import Herbie
import xarray as xr
import numpy as np

import matplotlib.pyplot as plt
from herbie.toolbox import EasyMap, pc
import cartopy.crs as ccrs
import cartopy.feature as feature
import pandas as pd

recent = pd.Timestamp("now").floor("6H") - pd.Timedelta("6H")

# Some examples
fxxs = range(1,48)


# loading more than one variable requires a loop, because the
# data is stored in multiple files (and a Herbie object only
# represents a single file).
#"VISIFG", "VISLFG" ,"Sfc","Sfc"

points_stations = pd.DataFrame(
        {
            "longitude" : [-73.7500, -75.6667,-77.7833,-71.6833,-71.4000,-72.2667,-77.7000,-68.2000,-66.2500,-72.6792,-74.0333,-74.6167,-68.2167,-66.8667,-73.6667,-79.4167,-64.4833,-73.7419,-61.778056],
            "latitude" : [45.466, 45.3167, 48.0500, 45.4333, 46.8000, 48.5167, 53.6333, 49.1333, 50.2167, 46.3539, 45.6833, 47.9167, 48.6167,52.9333,53.7500,46.3667,48.7833,45.4678,47.425],
            "stid": ['CYUL', 'CYOW', 'CYVO', 'CYSC','CYQB','CYRJ','CYGL','CYBC','CYZV','CYRQ','CYMX','CWPK','CYYY','CYWK','CYAH','CYYB','CYGP','CWTQ','CYGR']
        }
    )

store = []
for var, lev in zip(["UGRD", "VGRD", "GUST","GUST-Min","GUST-Max","WDIR" ], ["AGL-10m", "AGL-10m", "AGL-10m", "AGL-10m", "AGL-10m","AGL-10m"]):#,, "TMP" "GUST", "AGL-10m""AGL-2m"
    _ds = Herbie(
        recent,
        model="hrdps",
        fxx=0,
        product="continental",
        variable=var,
        level=lev,
    ).xarray()
    store.append(_ds)

ds = xr.merge(store)
print(ds)

#https://herbie.readthedocs.io/en/stable/gallery/eccc_models/hrdps.html
#https://www.partow.net/miscellaneous/airportdatabase/
for fxx in fxxs:
    store = []
    for var, lev in zip(["PRATE","CAPE"], ["Sfc","Sfc"]):#,, "TMP" "GUST", "AGL-10m""AGL-2m","SWEAT"
        _ds = Herbie(
            recent,
            model="hrdps",
            fxx=fxx,#prate n'a pas de zero
            product="continental",
            variable=var,
            level=lev,
        ).xarray()
        store.append(_ds)

    ds = xr.merge(store)
    print(ds)
    dsp = ds.herbie.pick_points(points_stations, method='nearest')
    print(dsp)
    df = dsp.compute().to_dataframe().reset_index()#.drop(['gribfile_projection','point_grid_distance','index','point','heightAboveGround'], axis=1) 
    df.to_csv(f'/home/da8073/bitbucket/hrrr_download/{recent}_hrrr_forecast_horizon_{fxx}.csv', index=False)


