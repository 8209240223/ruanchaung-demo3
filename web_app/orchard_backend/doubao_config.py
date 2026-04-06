# -*- coding: utf-8 -*-
"""
火山方舟 OpenAI 兼容接口配置。

请勿在代码中写入真实密钥。在系统环境变量中设置：
  DOUBAO_API_KEY
可选：
  DOUBAO_API_ENDPOINT（默认北京方舟 chat completions）
  DOUBAO_MODEL
API 说明：https://www.volcengine.com/docs/82379
"""

import os

DOUBAO_API_KEY = (os.getenv('DOUBAO_API_KEY') or '').strip()
DOUBAO_API_ENDPOINT = (os.getenv('DOUBAO_API_ENDPOINT') or '').strip() or (
    'https://ark.cn-beijing.volces.com/api/v3/chat/completions'
)
DOUBAO_MODEL = (os.getenv('DOUBAO_MODEL') or '').strip() or 'doubao-seed-1-6-251015'


def check_config():
    if not DOUBAO_API_KEY or DOUBAO_API_KEY == 'your-api-key-here':
        return False, '云端 API 密钥未配置（请设置环境变量 DOUBAO_API_KEY）'
    return True, '配置正常'


if __name__ == '__main__':
    ok, msg = check_config()
    print('配置状态:', msg)
