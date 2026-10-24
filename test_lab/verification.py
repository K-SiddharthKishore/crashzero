"""Server-side, two-image verification of Stage 1 accident candidates."""
import base64
import hashlib
import json
import os
from pathlib import Path


CLASSIFICATIONS = {'LIKELY_ACCIDENT', 'NO_ACCIDENT_EVIDENCE', 'UNCERTAIN'}
PROMPT = ("You are reviewing exactly two traffic-camera frames selected around a local model's "
          "suspected event, about one second apart. The local suspicion is not evidence by itself. "
          "Classify only what is visibly supported in these frames. Return LIKELY_ACCIDENT if "
          "there is clear collision/contact OR strong visible crash aftermath, even when the "
          "instant of impact is absent: for example an overturned vehicle, obvious fresh crash "
          "damage/debris tied to vehicles, a rider down beside a fallen motorcycle, or vehicles "
          "in unmistakably abnormal post-impact positions. Do not require the exact impact frame. "
          "Return NO_ACCIDENT_EVIDENCE when the pair shows ordinary traffic moving or waiting "
          "normally, without collision or strong aftermath evidence; this is a finding about these "
          "frames only, not proof that no accident happened elsewhere. Close spacing, crossing "
          "paths, a parked or merely fallen bicycle, an isolated roadside tire, or vehicles simply "
          "stopped are not by themselves evidence of a crash. Return UNCERTAIN when occlusion, "
          "poor visibility, or genuinely ambiguous aftermath prevents a supported positive or "
          "negative judgment. Do not invent unseen motion, damage, injuries, or causation. "
          "Explain the decisive visible reason in under 50 words; give at most three short "
          "visible_evidence items and three short limitations. No confidence percentages.")
VERIFICATION_POLICY = hashlib.sha256(PROMPT.encode()).hexdigest()[:12]
SCHEMA = {'type': 'object', 'properties': {
    'classification': {'type': 'string', 'enum': sorted(CLASSIFICATIONS)},
    'explanation': {'type': 'string'},
    'visible_evidence': {'type': 'array', 'items': {'type': 'string'}},
    'limitations': {'type': 'array', 'items': {'type': 'string'}}},
    'required': ['classification', 'explanation', 'visible_evidence', 'limitations'],
    'additionalProperties': False}


def settings():
    return {
        'model': os.getenv('OPENAI_VISION_MODEL', 'gpt-5.4-nano'),
        'max_requests_per_video': max(0, int(os.getenv('OPENAI_MAX_REQUESTS_PER_VIDEO', '3'))),
        'budget_usd': max(0., float(os.getenv('OPENAI_SESSION_BUDGET_USD', '0.50'))),
        'input_rate': max(0., float(os.getenv('OPENAI_INPUT_USD_PER_MILLION', '0.20'))),
        'output_rate': max(0., float(os.getenv('OPENAI_OUTPUT_USD_PER_MILLION', '1.25'))),
        'estimated_input_tokens': max(1, int(os.getenv('OPENAI_ESTIMATED_INPUT_TOKENS', '20000'))),
        'estimated_output_tokens': max(1, int(os.getenv('OPENAI_ESTIMATED_OUTPUT_TOKENS', '1200'))),
        'inr_per_usd': max(0., float(os.getenv('OPENAI_INR_PER_USD', '85'))),
    }


def cost_usd(input_tokens, output_tokens, config):
    return (input_tokens * config['input_rate'] + output_tokens * config['output_rate']) / 1_000_000


def estimated_request_cost(config):
    return cost_usd(config['estimated_input_tokens'], config['estimated_output_tokens'], config)


def verify_pair(paths, model, client=None):
    if len(paths) != 2:
        raise ValueError('Exactly two evidence images are required.')
    if client is None:
        if not os.getenv('OPENAI_API_KEY'):
            raise RuntimeError('OPENAI_API_KEY is not configured.')
        from openai import OpenAI
        client = OpenAI(timeout=30.0, max_retries=0)
    content = [{'type': 'input_text', 'text': PROMPT}]
    for path in paths:
        data = base64.b64encode(Path(path).read_bytes()).decode('ascii')
        content.append({'type': 'input_image', 'image_url': 'data:image/jpeg;base64,' + data,
                        'detail': 'high'})
    response = client.responses.create(
        model=model, input=[{'role': 'user', 'content': content}],
        text={'format': {'type': 'json_schema', 'name': 'accident_verification',
                         'schema': SCHEMA, 'strict': True}},
        max_output_tokens=1200, store=False)
    if getattr(response, 'status', 'completed') != 'completed':
        raise ValueError('OpenAI response was incomplete.')
    value = json.loads(response.output_text)
    if (not isinstance(value, dict) or value.get('classification') not in CLASSIFICATIONS
            or not isinstance(value.get('explanation'), str)
            or not isinstance(value.get('visible_evidence'), list)
            or not all(isinstance(item, str) for item in value['visible_evidence'])
            or not isinstance(value.get('limitations'), list)
            or not all(isinstance(item, str) for item in value['limitations'])):
        raise ValueError('Invalid verification response.')
    usage = getattr(response, 'usage', None)
    return value | {'input_tokens': getattr(usage, 'input_tokens', None),
                    'output_tokens': getattr(usage, 'output_tokens', None), 'model': model}


def safe_failure(exc):
    """Provide actionable diagnostics without leaking request contents or API keys."""
    status = getattr(exc, 'status_code', None)
    code = getattr(exc, 'code', None)
    if status is not None:
        return f'OpenAI API {status}' + (f' ({code})' if code else '') + '.'
    if isinstance(exc, json.JSONDecodeError):
        return 'OpenAI returned incomplete or invalid JSON.'
    if isinstance(exc, ValueError):
        return str(exc)[:120]
    return f'{type(exc).__name__} while contacting OpenAI.'
