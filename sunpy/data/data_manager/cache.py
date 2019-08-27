import os
from pathlib import Path
from datetime import datetime, timedelta
from warnings import warn
from urllib.request import urlopen

import astropy.units as u
from astropy.time import TimeDelta

from sunpy.data.data_manager.downloader import DownloaderError
from sunpy.util.exceptions import SunpyUserWarning
from sunpy.util.net import get_filename
from sunpy.util.util import hash_file, replacement_filename

__all__ = ['Cache']


class Cache:
    """
    Cache provides a way to download and cache files.

    Parameters
    ----------
    downloader: Implementation of `~sunpy.data.data_manager.downloader.DownloaderBase`
        Downloader object for downloading remote files.
    storage: Implementation of `~sunpy.data.data_manager.storage.StorageProviderBase`
        Storage to store metadata about the files.
    cache_dir: `str` or `pathlib.Path`
        Directory where the downloaded files will be stored.
    expiry: `astropy.units.quantity.Quantity` or `None`, optional
        The interval after which the cache is invalidated. If the expiry is `None`,
        then the expiry is not checked (or the cache never expires). Defaults to 10 seconds.
    """

    def __init__(self, downloader, storage, cache_dir, expiry=10*u.s):
        self._downloader = downloader
        self._storage = storage
        self._cache_dir = Path(cache_dir)
        self._expiry = expiry if expiry is None else TimeDelta(expiry)

    def download(self, urls, redownload=False):
        """
        Downloads the files from the urls.

        Parameters
        ----------
        urls: `list` or `str`
            A list of urls or a single url.
        redownload: `bool`
            Whether to skip cache and redownload.

        Returns
        -------
        `pathlib.PosixPath`
            Path to the downloaded file.
        """
        if isinstance(urls, str):
            urls = [urls]
        # Program flow
        # 1. If redownload: Don't check cache, don't put in cache. Download and return file path
        # 2. If not redownload: Check cache,
        #    i. If present in cache:
        #        - If cache expired, remove entry from cache, download and add to cache
        #        - If cache not expired, return path
        #    ii. If not download, store in cache and return path
        if not redownload:
            details = None
            for url in urls:
                details = self._get_by_url(url)
                if details:
                    break
            if details:
                if self._expiry and \
                   datetime.now() - datetime.fromisoformat(details['time']) > self._expiry:
                    os.remove(details['file_path'])
                    self._storage.delete_by_key('url', details['url'])
                else:
                    return Path(details['file_path'])

        file_path, file_hash, url = self._download_and_hash(urls)

        if not redownload:
            self._storage.store({
                'file_hash': file_hash,
                'file_path': str(file_path),
                'url': url,
                'time': datetime.now().isoformat(),
            })
        return file_path

    def get_by_hash(self, sha_hash):
        """
        Returns the details which is matched by hash if present in cache.

        Parameters
        ----------
        sha_hash: `str`
            SHA-1 hash of the file.
        """
        details = self._storage.find_by_key('file_hash', sha_hash)
        return details

    def _get_by_url(self, url):
        """
        Returns the details which is matched by url if present in cache.

        Parameters
        ----------
        url: `str`
            URL of the file.
        """
        details = self._storage.find_by_key('url', url)
        return details

    def _download_and_hash(self, urls):
        """
        Downloads the file and returns the path, hash and url it used to download.

        Parameters
        ----------
        urls: `list`
            List of urls.

        Returns
        -------
        `str`, `str`, `str`
            Path, hash and URL of the file.
        """
        def download(url):
            path = self._cache_dir / get_filename(urlopen(url), url)
            path = replacement_filename(path)
            self._downloader.download(url, path)
            shahash = hash_file(path)
            return path, shahash, url

        for url in urls:
            try:
                return download(url)
            except Exception as e:
                warn(e, SunpyUserWarning)
        else:
            raise RuntimeError("Download failed")
