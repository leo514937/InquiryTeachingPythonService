import httpx


class ModelUnavailable(RuntimeError):
    """No production model result is available; never substitute mock text."""
    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


class StrictLLM:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client

    def complete(self, system_prompt, message):
        if not self.settings.llm_api_key:
            raise ModelUnavailable('模型未配置')
        url = self.settings.llm_api_base.rstrip('/') + '/chat/completions'
        payload = {'model': self.settings.llm_model, 'messages': [
            {'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': message},
        ], 'temperature': 0.2, 'stream': False}
        headers = {'Authorization': 'Bearer ' + self.settings.llm_api_key}
        try:
            if self.client is not None:
                response = self.client.post(url, json=payload, headers=headers, timeout=90)
            else:
                with httpx.Client(timeout=90) as client:
                    response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
            if not isinstance(content, str) or not content.strip():
                raise ValueError('empty response')
            return content
        except httpx.HTTPStatusError as exc:
            raise ModelUnavailable('模型调用失败，请检查配置后重试', retryable=exc.response.status_code == 429 or exc.response.status_code >= 500) from exc
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ModelUnavailable('模型调用失败，请检查配置后重试', retryable=True) from exc
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            # The original error may contain credentials or model input.
            raise ModelUnavailable('模型调用失败，请检查配置后重试') from exc
