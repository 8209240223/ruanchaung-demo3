# -*- coding: utf-8 -*-
"""
火山方舟 OpenAI 兼容接口：下面三行改一次即可，Web 与说明文档都读这里。无需配环境变量。
API 说明：https://www.volcengine.com/docs/82379
"""

DOUBAO_API_KEY = '501eef5d-21d4-4df6-bdcb-6e98ad79ed48'
DOUBAO_API_ENDPOINT = 'https://ark.cn-beijing.volces.com/api/v3/chat/completions'
DOUBAO_MODEL = 'doubao-seed-1-6-251015'


def check_config():
    if not DOUBAO_API_KEY or DOUBAO_API_KEY == 'your-api-key-here':
        return False, '云端 API 密钥未配置'
    return True, '配置正常'


if __name__ == '__main__':
    ok, msg = check_config()
    print('配置状态:', msg)
