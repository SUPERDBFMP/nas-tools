import json
import os.path
import re
import sys
import tempfile
import time
import zipfile
from functools import reduce
from threading import Lock

import requests
import undetected_chromedriver as uc
from webdriver_manager.chrome import ChromeDriverManager

from app.utils import SystemUtils, RequestUtils

try:
    import winreg
except ImportError:
    winreg = None

lock = Lock()

driver_executable_path = None

CHROME_FOR_TESTING_BUILD_URL = "https://googlechromelabs.github.io/chrome-for-testing/latest-patch-versions-per-build-with-downloads.json"
CHROME_FOR_TESTING_STABLE_URL = "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"


class ChromeHelper(object):
    _executable_path = None

    _chrome = None
    _headless = False

    def __init__(self, headless=False):

        self._executable_path = SystemUtils.get_webdriver_path() or driver_executable_path

        if SystemUtils.is_windows():
            self._headless = False
        elif not os.environ.get("NASTOOL_DISPLAY"):
            self._headless = True
        else:
            self._headless = headless

    def init_driver(self):
        if self._executable_path:
            return
        if not uc.find_chrome_executable():
            return
        global driver_executable_path
        chrome_version = self.__get_chrome_version()
        if chrome_version and int(chrome_version.split(".")[0]) >= 115:
            try:
                driver_executable_path = self.__install_chrome_for_testing_driver()
            except Exception as err:
                print("ChromeDriver 初始化失败，浏览器渲染相关功能将不可用：%s" % str(err))
                driver_executable_path = None
            return
        try:
            driver_executable_path = ChromeDriverManager().install()
        except Exception as err:
            try:
                driver_executable_path = self.__install_chrome_for_testing_driver()
            except Exception as fallback_err:
                print("ChromeDriver 初始化失败，浏览器渲染相关功能将不可用：%s；%s"
                      % (str(err), str(fallback_err)))
                driver_executable_path = None

    def __install_chrome_for_testing_driver(self):
        chrome_version = self.__get_chrome_version()
        cft_platform = self.__get_chrome_for_testing_platform()
        driver_info = self.__get_chrome_for_testing_driver(chrome_version, cft_platform)
        driver_version = driver_info.get("version")
        driver_url = driver_info.get("url")
        if not driver_version or not driver_url:
            raise RuntimeError("未找到可用的 ChromeDriver 下载地址")
        driver_filename = "chromedriver.exe" if SystemUtils.is_windows() else "chromedriver"
        driver_cache_path = os.path.join(tempfile.gettempdir(), "nastool-chromedriver",
                                         driver_version, cft_platform, driver_filename)
        if os.path.exists(driver_cache_path):
            return driver_cache_path
        os.makedirs(os.path.dirname(driver_cache_path), exist_ok=True)
        zip_path = os.path.join(tempfile.gettempdir(), "nastool-chromedriver", "%s-%s.zip"
                                % (driver_version, cft_platform))
        response = requests.get(driver_url, timeout=30)
        response.raise_for_status()
        with open(zip_path, "wb") as zip_file:
            zip_file.write(response.content)
        with zipfile.ZipFile(zip_path) as driver_zip:
            driver_zip.extractall(os.path.dirname(driver_cache_path))
        for root, _, files in os.walk(os.path.dirname(driver_cache_path)):
            if driver_filename in files:
                extracted_path = os.path.join(root, driver_filename)
                if extracted_path != driver_cache_path:
                    os.replace(extracted_path, driver_cache_path)
                if not SystemUtils.is_windows():
                    os.chmod(driver_cache_path, 0o755)
                print("已安装 ChromeDriver：%s" % driver_cache_path)
                return driver_cache_path
        raise RuntimeError("ChromeDriver 压缩包中未找到 %s" % driver_filename)

    def __get_chrome_for_testing_driver(self, chrome_version, cft_platform):
        build = ".".join(chrome_version.split(".")[:3]) if chrome_version else ""
        if build:
            build_data = requests.get(CHROME_FOR_TESTING_BUILD_URL, timeout=10).json()
            build_info = (build_data.get("builds") or {}).get(build)
            if build_info:
                driver_url = self.__get_driver_url(build_info, cft_platform)
                if driver_url:
                    return {"version": build_info.get("version"), "url": driver_url}
        stable_data = requests.get(CHROME_FOR_TESTING_STABLE_URL, timeout=10).json()
        stable_info = (stable_data.get("channels") or {}).get("Stable") or {}
        return {"version": stable_info.get("version"),
                "url": self.__get_driver_url(stable_info, cft_platform)}

    @staticmethod
    def __get_driver_url(version_info, cft_platform):
        for driver in ((version_info.get("downloads") or {}).get("chromedriver") or []):
            if driver.get("platform") == cft_platform:
                return driver.get("url")
        return None

    @staticmethod
    def __get_chrome_for_testing_platform():
        if SystemUtils.is_windows():
            return "win64" if sys.maxsize > 2 ** 32 else "win32"
        if SystemUtils.is_macos():
            return "mac-arm64" if "arm" in os.uname().machine.lower() else "mac-x64"
        return "linux64"

    @staticmethod
    def __get_chrome_version():
        if SystemUtils.is_windows():
            for key_root, key_path in (
                    (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon"),
                    (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Chrome\BLBeacon"),
                    (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Google\Chrome\BLBeacon")):
                try:
                    with winreg.OpenKey(key_root, key_path) as chrome_key:
                        return winreg.QueryValueEx(chrome_key, "version")[0]
                except OSError:
                    pass
            return None
        chrome = uc.find_chrome_executable()
        if not chrome:
            return None
        output = os.popen('"%s" --version' % chrome).read()
        match = re.search(r"(\d+\.\d+\.\d+\.\d+)", output)
        return match.group(1) if match else None

    @property
    def browser(self):
        with lock:
            if not self._chrome:
                self._chrome = self.__get_browser()
            return self._chrome

    def get_status(self):
        if not self._executable_path:
            return False
        if self._executable_path \
                and not os.path.exists(self._executable_path):
            return False
        if not uc.find_chrome_executable():
            return False
        return True

    def __get_browser(self):
        if not self.get_status():
            return None
        options = uc.ChromeOptions()
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins-discovery")
        options.add_argument('--no-first-run')
        options.add_argument('--no-service-autorun')
        options.add_argument('--no-default-browser-check')
        options.add_argument('--password-store=basic')
        if self._headless:
            options.add_argument('--headless')
        prefs = {
            "useAutomationExtension": False,
            "profile.managed_default_content_settings.images": 2 if self._headless else 1,
            "excludeSwitches": ["enable-automation"]
        }
        options.add_experimental_option("prefs", prefs)
        chrome = ChromeWithPrefs(options=options, driver_executable_path=self._executable_path)
        chrome.set_page_load_timeout(30)
        return chrome

    def visit(self, url, ua=None, cookie=None, timeout=30):
        if not self.browser:
            return False
        try:
            if ua:
                self._chrome.execute_cdp_cmd("Emulation.setUserAgentOverride", {
                    "userAgent": ua
                })
            if timeout:
                self._chrome.implicitly_wait(timeout)
            self._chrome.get(url)
            if cookie:
                self._chrome.delete_all_cookies()
                for cookie in RequestUtils.cookie_parse(cookie, array=True):
                    self._chrome.add_cookie(cookie)
                self._chrome.get(url)
            return True
        except Exception as err:
            print(str(err))
            return False

    def new_tab(self, url, ua=None, cookie=None):
        if not self._chrome:
            return False
        # 新开一个标签页
        try:
            self._chrome.switch_to.new_window('tab')
        except Exception as err:
            print(str(err))
            return False
        # 访问URL
        return self.visit(url=url, ua=ua, cookie=cookie)

    def close_tab(self):
        try:
            self._chrome.close()
            self._chrome.switch_to.window(self._chrome.window_handles[0])
        except Exception as err:
            print(str(err))
            return False

    def pass_cloudflare(self, waittime=10):
        cloudflare = False
        for i in range(0, waittime):
            if self.get_title() != "Just a moment...":
                cloudflare = True
                break
            time.sleep(1)
        return cloudflare

    def execute_script(self, script):
        if not self._chrome:
            return False
        try:
            return self._chrome.execute_script(script)
        except Exception as err:
            print(str(err))

    def get_title(self):
        if not self._chrome:
            return ""
        return self._chrome.title

    def get_html(self):
        if not self._chrome:
            return ""
        return self._chrome.page_source

    def get_cookies(self):
        if not self._chrome:
            return ""
        cookie_str = ""
        try:
            for _cookie in self._chrome.get_cookies():
                if not _cookie:
                    continue
                cookie_str += "%s=%s;" % (_cookie.get("name"), _cookie.get("value"))
        except Exception as err:
            print(str(err))
        return cookie_str

    def get_ua(self):
        try:
            return self._chrome.execute_script("return navigator.userAgent")
        except Exception as err:
            print(str(err))
            return None

    def quit(self):
        if self._chrome:
            self._chrome.close()
            self._chrome.quit()
            self._fixup_uc_pid_leak()
            self._chrome = None

    def _fixup_uc_pid_leak(self):
        """
        uc 在处理退出时为强制kill进程，没有调用wait，会导致出现僵尸进程，此处增加wait，确保系统正常回收
        :return:
        """
        try:
            # chromedriver 进程
            if hasattr(self._chrome, "service") and getattr(self._chrome.service, "process", None):
                self._chrome.service.process.wait(3)
            # chrome 进程
            os.waitpid(self._chrome.browser_pid, 0)
        except Exception as e:
            print(str(e))
            pass

    def __del__(self):
        self.quit()


class ChromeWithPrefs(uc.Chrome):
    def __init__(self, *args, options=None, **kwargs):
        if options:
            self._handle_prefs(options)
        super().__init__(*args, options=options, **kwargs)
        # remove the user_data_dir when quitting
        self.keep_user_data_dir = False

    @staticmethod
    def _handle_prefs(options):
        if prefs := options.experimental_options.get("prefs"):
            # turn a (dotted key, value) into a proper nested dict
            def undot_key(key, value):
                if "." in key:
                    key, rest = key.split(".", 1)
                    value = undot_key(rest, value)
                return {key: value}

            # undot prefs dict keys
            undot_prefs = reduce(
                lambda d1, d2: {**d1, **d2},  # merge dicts
                (undot_key(key, value) for key, value in prefs.items()),
            )

            # create a user_data_dir and add its path to the options
            user_data_dir = os.path.normpath(tempfile.mkdtemp())
            options.add_argument(f"--user-data-dir={user_data_dir}")

            # create the preferences json file in its default directory
            default_dir = os.path.join(user_data_dir, "Default")
            os.mkdir(default_dir)

            prefs_file = os.path.join(default_dir, "Preferences")
            with open(prefs_file, encoding="latin1", mode="w") as f:
                json.dump(undot_prefs, f)

            # pylint: disable=protected-access
            # remove the experimental_options to avoid an error
            del options._experimental_options["prefs"]
