"""Safe asset-discovery boundary for future typed world authoring.

The v0 Isaac scene has no verified spawnable asset yet.  Keeping this tiny
catalog explicit prevents a research model from treating the container
filesystem as an asset search API.
"""

from __future__ import annotations

from dataclasses import dataclass


class AssetCatalogError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class AssetMetadata:
    asset_id: str
    display_name: str
    source: str
    usd_reference: str
    category: str
    compatibility_notes: str = ""


class AssetCatalog:
    """Curated manifest only; never enumerates arbitrary host/container paths."""

    def __init__(self, assets: tuple[AssetMetadata, ...] = ()) -> None:
        self._assets = {asset.asset_id: asset for asset in assets}

    def list_asset_categories(self) -> tuple[str, ...]:
        return tuple(sorted({asset.category for asset in self._assets.values()}))

    def search_assets(self, query: str, *, category: str | None = None, limit: int = 20) -> tuple[AssetMetadata, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        needle = query.casefold().strip()
        return tuple(
            asset for asset in self._assets.values()
            if (category is None or asset.category == category)
            and (not needle or needle in f"{asset.asset_id} {asset.display_name} {asset.category}".casefold())
        )[:limit]

    def inspect_asset(self, asset_id: str) -> AssetMetadata:
        try:
            return self._assets[asset_id]
        except KeyError as error:
            raise AssetCatalogError("ASSET_NOT_AVAILABLE", f"asset is not in the verified catalog: {asset_id}") from error


def isaac_v0_asset_catalog() -> AssetCatalog:
    """No spawning is advertised until an asset is verified in Isaac 6.0.1."""
    return AssetCatalog()
