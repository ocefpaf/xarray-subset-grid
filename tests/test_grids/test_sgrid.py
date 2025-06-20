from pathlib import Path

import numpy as np
import pytest
import xarray as xr

import xarray_subset_grid.accessor  # noqa: F401
from xarray_subset_grid.grids.sgrid import _get_location_info_from_topology

# open dataset as zarr object using fsspec reference file system and xarray
try:
    import fsspec
    import zarr

    zarr__version__ = int(zarr.__version__.split(".")[0])
except ImportError:
    fsspec = None


test_dir = Path(__file__).parent.parent / "example_data"

sample_sgrid_file = test_dir / "arakawa_c_test_grid.nc"


def test_grid_topology_location_parse():
    ds = xr.open_dataset(sample_sgrid_file, decode_times=False)
    node_info = _get_location_info_from_topology(ds["grid"], "node")
    edge1_info = _get_location_info_from_topology(ds["grid"], "edge1")
    edge2_info = _get_location_info_from_topology(ds["grid"], "edge2")
    face_info = _get_location_info_from_topology(ds["grid"], "face")

    assert node_info == {
        "dims": ["xi_psi", "eta_psi"],
        "coords": ["lon_psi", "lat_psi"],
        "padding": {"xi_psi": "none", "eta_psi": "none"},
    }
    assert edge1_info == {
        "dims": ["xi_u", "eta_u"],
        "coords": ["lon_u", "lat_u"],
        "padding": {"eta_u": "both", "xi_u": "none"},
    }
    assert edge2_info == {
        "dims": ["xi_v", "eta_v"],
        "coords": ["lon_v", "lat_v"],
        "padding": {"xi_v": "both", "eta_v": "none"},
    }
    assert face_info == {
        "dims": ["xi_rho", "eta_rho"],
        "coords": ["lon_rho", "lat_rho"],
        "padding": {"xi_rho": "both", "eta_rho": "both"},
    }


@pytest.mark.skipif(
    zarr__version__ >= 3, reason="zarr3.0.8 doesn't support FSpec AWS (it might soon)"
)
@pytest.mark.online
def test_polygon_subset():
    """
    This is a basic integration test for the subsetting of a ROMS sgrid dataset using
    a polygon.
    """
    if fsspec is None:
        raise ImportError("Must have fsspec installed to run --online tests")
    fs = fsspec.filesystem(
        "reference",
        fo="s3://noaa-nodd-kerchunk-pds/nos/wcofs/wcofs.fields.best.nc.zarr",
        remote_protocol="s3",
        remote_options={"anon": True},
        target_protocol="s3",
        target_options={"anon": True},
    )
    m = fs.get_mapper("")

    ds = xr.open_dataset(m, engine="zarr", backend_kwargs=dict(consolidated=False), chunks={})

    polygon = np.array(
        [
            [-122.38488806417945, 34.98888604471138],
            [-122.02425311530737, 33.300351211467074],
            [-120.60402628930146, 32.723214427630836],
            [-116.63789131284673, 32.54346959375448],
            [-116.39346090873218, 33.8541384965596],
            [-118.83845767505964, 35.257586401855164],
            [-121.34541503969862, 35.50073821008141],
            [-122.38488806417945, 34.98888604471138],
        ]
    )
    ds_temp = ds.xsg.subset_vars(["temp", "u", "v"])
    ds_subset = ds_temp.xsg.subset_polygon(polygon)

    # Check that the subset dataset has the correct dimensions given the original padding
    assert ds_subset.sizes["eta_rho"] == ds_subset.sizes["eta_psi"] + 1
    assert ds_subset.sizes["eta_u"] == ds_subset.sizes["eta_psi"] + 1
    assert ds_subset.sizes["eta_v"] == ds_subset.sizes["eta_psi"]
    assert ds_subset.sizes["xi_rho"] == ds_subset.sizes["xi_psi"] + 1
    assert ds_subset.sizes["xi_u"] == ds_subset.sizes["xi_psi"]
    assert ds_subset.sizes["xi_v"] == ds_subset.sizes["xi_psi"] + 1

    # Check that the subset rho/psi/u/v positional relationship makes sense aka psi point is
    # 'between' it's neighbor rho points
    # Note that this needs to be better generalized; it's not trivial to write a test that
    # works in all potential cases.
    assert (
        ds_subset["lon_rho"][0, 0] < ds_subset["lon_psi"][0, 0]
        and ds_subset["lon_rho"][0, 1] > ds_subset["lon_psi"][0, 0]
    )

    # ds_subset.temp_sur.isel(ocean_time=0).plot(x="lon_rho", y="lat_rho")


def test_polygon_subset_2():
    ds = xr.open_dataset(sample_sgrid_file, decode_times=False)
    polygon = np.array([[6.5, 37.5], [6.5, 39.5], [9.5, 40.5], [8.5, 37.5], [6.5, 37.5]])
    ds_subset = ds.xsg.subset_polygon(polygon)

    # Check that the subset dataset has the correct dimensions given the original padding
    assert ds_subset.sizes["eta_rho"] == ds_subset.sizes["eta_psi"] + 1
    assert ds_subset.sizes["eta_u"] == ds_subset.sizes["eta_psi"] + 1
    assert ds_subset.sizes["eta_v"] == ds_subset.sizes["eta_psi"]
    assert ds_subset.sizes["xi_rho"] == ds_subset.sizes["xi_psi"] + 1
    assert ds_subset.sizes["xi_u"] == ds_subset.sizes["xi_psi"]
    assert ds_subset.sizes["xi_v"] == ds_subset.sizes["xi_psi"] + 1

    assert ds_subset.lon_psi.min() <= 6.5 and ds_subset.lon_psi.max() >= 9.5
    assert ds_subset.lat_psi.min() <= 37.5 and ds_subset.lat_psi.max() >= 40.5

    assert "u" in ds_subset.variables.keys()
