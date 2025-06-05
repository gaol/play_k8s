#!/bin/python

import os
import urllib.request
import zipfile

# maybe we don't need to download it manually, terraform will download it automatically
def prepare_terraform_provider_libvirt(ver: str):
    plugin_dir = os.path.join(os.path.expanduser("~"), ".terraform.d", "plugins", "terraform-provider-libvirt")
    if not os.path.isdir(plugin_dir):
        print(f"Creating directory: {plugin_dir}")
        os.makedirs(plugin_dir)
    plugin_exec_file = os.path.join(plugin_dir, f"terraform-provider-libvirt_v{ver}")
    if not os.path.isfile(plugin_exec_file):
        url = f"https://github.com/dmacvicar/terraform-provider-libvirt/releases/download/v{ver}/terraform-provider-libvirt_{ver}_linux_arm64.zip"
        download_path = os.path.join(plugin_dir, f"terraform-provider-libvirt_{ver}_linux_arm64.zip")
        print(f"Downloading {url} ...")
        urllib.request.urlretrieve(url, download_path)
        print("Download completed")
        with zipfile.ZipFile(download_path, 'r') as zip_ref:
          zip_ref.extractall(plugin_dir)
        os.chmod(plugin_exec_file, 0o755)


def main():
    prepare_terraform_provider_libvirt("0.8.3")

if __name__ == "__main__":
    main()