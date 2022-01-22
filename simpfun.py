import functools
import io
import logging
import os
import subprocess
import sys
import threading
import time
import traceback
from functools import wraps

import requests
from PIL import Image
from PIL.ImageFile import ImageFile
from ruamel.yaml import YAML, CommentedMap


def try_except(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = False
        try:
            result = func(*args, **kwargs)
        except KeyboardInterrupt:
            raise
        except Exception:
            traceback.print_exc()
            pass
        return result

    return wrapper


@try_except
def send_message(group_id, message):
    data = {'group_id': group_id, 'message': message}
    r = requests.post(API_ROOT + '/send_group_msg', data=data, timeout=3)
    if r.json().get('retcode') == 0:
        return True
    return False


class Simpfun:
    def __init__(self, username, password, sf_userdata=None):
        self.username = username
        self.password = password
        self.sf_userdata = sf_userdata
        self.headers = {'User-Agent': None}
        self.img = None
        self.PHPSESSID = None
        self.code = None
        self.verify = True
        self.result = None
        self.logger = logging.getLogger('Simpfun')

    def __del__(self):
        del self
        return False

    def _reset_var(self):
        self.img = None
        self.PHPSESSID = None
        self.code = None
        self.verify = True
        self.result = None

    def sign(self):
        if not self.sf_userdata:
            self.logger.info('开始登录')
            if not self.login():
                self.logger.error('登录失败')
                return self.__del__()
            self.logger.info('登录成功')
        self._reset_var()
        self.logger.info('开始获取图片')
        if not self._get_img():
            self.logger.error('获取图片失败')
            return self.__del__()
        self.logger.info('获取图片成功')
        self.logger.info('开始获取偏移')
        if not self._get_code():
            self.logger.error('获取偏移失败')
            return self.__del__()
        self.logger.info(f'偏移：{self.code}')
        self.logger.info('开始签到')
        if not self._sign():
            self.logger.error('签到失败')
            return self.__del__()
        self.logger.info(f'签到成功：{self.result}')
        return True

    @try_except
    def login(self):
        if not self.username or not self.password:
            return False
        data = {'QQ': self.username, 'pass': self.password}
        url = 'https://sfe.simpfun.cn/login-redirect.php'
        r = requests.post(url, data, headers=self.headers, verify=self.verify)
        cookies: dict = r.cookies.get_dict()
        self.sf_userdata = cookies.get('sf-userdata')
        if not self.sf_userdata:
            return False
        return True

    @try_except
    def _get_img(self):
        if not self.sf_userdata:
            self.__del__()
        url = 'https://sfe.simpfun.cn/sign_code/tncode.php'
        cookies = {'sf-userdata': self.sf_userdata}
        r = requests.get(url, headers=self.headers, cookies=cookies, verify=self.verify)
        cookies: dict = r.cookies.get_dict()
        self.PHPSESSID = cookies.get('PHPSESSID')
        if not self.PHPSESSID:
            self.logger.debug('获取PHPSESSID失败')
            return False
        self.logger.debug('获取PHPSESSID成功')
        img: ImageFile = Image.open(io.BytesIO(r.content))
        self.img = img
        return True

    @try_except
    def _get_code(self):
        if not self.img:
            return False
        img_x, img_y = self.img.size
        region1 = self.img.crop((0, 0, img_x, img_y / 3))
        region2 = self.img.crop((0, img_y / 3, img_x, img_y / 3 * 2))
        region3 = self.img.crop((0, img_y / 3 * 2, img_x, img_y))
        if LOG_LEVEL == logging.DEBUG:
            region1.show()
            region2.show()
            region3.show()
        region_x, region_y = region1.size
        first = 0
        last = 0
        for x in range(region_x):
            for y in range(region_y):
                pixel1 = region1.load()[x, y]
                pixel2 = region3.load()[x, y]
                if not self._compare_pixel(pixel1, pixel2):
                    self.logger.debug(x, y)
                    if not first:
                        first = x, y
                    last = x, y
        self.logger.debug(first + last)
        if LOG_LEVEL == logging.DEBUG:
            region1.crop(first + last).show()
        self.code = last[0] - 50
        return True

    @try_except
    def _compare_pixel(self, pixel1, pixel2):
        threshold = 60
        if abs(pixel1[0] - pixel2[0]) < threshold and abs(pixel1[1] - pixel2[1]) < threshold and abs(
                pixel1[2] - pixel2[2]) < threshold:
            return True
        return False

    @try_except
    def _sign(self):
        if not self.sf_userdata and not self.PHPSESSID:
            self.__del__()
        url = 'https://sfe.simpfun.cn/sign_code/check.php'
        cookies = {'sf-userdata': self.sf_userdata, 'PHPSESSID': self.PHPSESSID}
        params = {'tn_r': self.code}
        r = requests.get(url, params, headers=self.headers, cookies=cookies, verify=self.verify)
        self.result = r.text
        if self.result and self.result != 'error':
            return True
        return False


API_ROOT = 'http://127.0.0.1:5700'
wait_time = 10
cqhttp_path = 'go-cqhttp.exe'
LOG_LEVEL = logging.INFO
conf_path = 'config.yml'

if __name__ == '__main__':
    if '-d' in sys.argv[1:] or 'debug' in sys.argv[1:]:
        LOG_LEVEL = logging.DEBUG
    fmt_str = "[%(asctime)s] [%(levelname)s]: ╬ 简幻欢 ╬ ✺ %(message)s"
    logging.basicConfig(level=LOG_LEVEL,
                        format=fmt_str,
                        stream=sys.stdout,
                        datefmt="%Y-%m-%d %H:%M:%S")
    logger = logging.getLogger('Simpfun')
    if not os.path.exists(cqhttp_path):
        logger.error('请先下载go-cqhttp.exe - https://github.com/Mrs4s/go-cqhttp/releases')
        exit()
    if '-v' not in sys.argv[1:] and 'verbose' not in sys.argv[1:]:
        cqhttp_path += ' > nul'
    if '-i' in sys.argv[1:] or 'init' in sys.argv[1:] and os.path.exists(conf_path):
        os.remove(conf_path)
    yaml = YAML()
    conf: CommentedMap
    if not os.path.exists(conf_path):
        subprocess.Popen(f'echo 0 | {cqhttp_path} > nul', shell=True).wait()
    with open(conf_path, 'r', encoding='utf-8') as f:
        conf = yaml.load(f)
    account: CommentedMap = conf.get('account')
    servers: CommentedMap = conf.get('servers')
    qq_username = account.get('uin')
    qq_password = account.get('password')
    simpfun_username = account.get('simpfun_username')
    simpfun_password = account.get('simpfun_password')
    group_id = account.get('group_id')
    host = servers[0]['http']['host']
    port = servers[0]['http']['port']
    if host and port:
        API_ROOT = f'http://{host}:{port}'
    if not qq_username or not qq_password:
        qq_username = input('请输入qq账号：')
        conf['account']['uin'] = int(qq_username)
        qq_password = input('请输入qq密码：')
        conf['account']['password'] = qq_password
    if not simpfun_username or not simpfun_password:
        simpfun_username = input('请输入简幻欢账号：')
        conf['account']['simpfun_username'] = int(qq_username)
        simpfun_password = input('请输入简幻欢密码：')
        conf['account']['simpfun_password'] = simpfun_password
    if not group_id:
        group_id = input('请输入qq群号：')
        conf['account']['group_id'] = int(group_id)
    with open('config.yml', 'w', encoding='utf-8') as f:
        yaml.dump(conf, f)
    logger.info(f'等待{wait_time}秒开始签到')
    threading.Thread(target=functools.partial(subprocess.Popen, cqhttp_path, shell=True), daemon=True).start()
    time.sleep(wait_time)
    sf = Simpfun(simpfun_username, simpfun_password)
    if not sf.login():
        logger.info('登录失败')
        exit(1)
    logger.info('登录成功')
    while True:
        if sf.sign():
            logger.info(f'正在发送到群聊：{group_id}')
            n = 1
            while n <= 3:
                if send_message(group_id, sf.result):
                    logger.info('发送成功')
                    break
                else:
                    logger.error('发送失败')
                    logger.info(f'等待{wait_time}秒后重试')
                    time.sleep(wait_time)
                    n += 1
            logger.info('等待3小时')
            time.sleep(3600 * 3)
        else:
            logger.info(f'等待{wait_time}秒后重试')
            time.sleep(wait_time)
