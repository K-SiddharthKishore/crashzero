"""Provider boundaries: backend kill switch runs immediately before submission."""
import os
from .config import real_guard, submission_guard


class MockCallProvider:
    def submit(self, attempt): return 'mock-'+attempt['id'], 'COMPLETED'
    def status(self, provider_id): return 'COMPLETED'


class PlivoCallProvider:
    def submit(self, attempt):
        submission_guard(attempt,'plivo')
        import plivo
        client=plivo.RestClient(os.environ['PLIVO_AUTH_ID'],os.environ['PLIVO_AUTH_TOKEN'])
        base=os.environ['CALLBACK_BASE_URL'].rstrip('/')
        result=client.calls.create(from_=os.environ['PLIVO_FROM_NUMBER'],to_=attempt['destination'],
            answer_url=base+'/plivo/answer/'+attempt['token'],answer_method='POST',
            ring_url=base+'/plivo/status/'+attempt['token'],
            hangup_url=base+'/plivo/status/'+attempt['token'])
        return str(result.request_uuid),'INITIATED'

    def status(self, provider_id):
        real_guard()
        import plivo
        client=plivo.RestClient(os.environ['PLIVO_AUTH_ID'],os.environ['PLIVO_AUTH_TOKEN'])
        call=client.calls.get(provider_id)
        return normalize_status(getattr(call,'call_status','unknown'))


class ExotelCallProvider:
    """Voice v1 call-to-flow API with dynamic Greeting applet callback."""
    def _request(self, method, path, **kwargs):
        real_guard()
        import requests
        host=os.getenv('EXOTEL_API_HOST','api.in.exotel.com')
        if host not in ('api.in.exotel.com','api.exotel.com'): raise ValueError('Invalid Exotel API region.')
        base='https://'+host+'/v1/Accounts/'+os.environ['EXOTEL_ACCOUNT_SID']
        response=requests.request(method,base+path,auth=(os.environ['EXOTEL_API_KEY'],os.environ['EXOTEL_API_TOKEN']),timeout=15,**kwargs)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def payload(attempt):
        return {'From':attempt['destination'], 'CallerId':os.environ['EXOTEL_CALLER_ID'],
            'Url':os.environ['EXOTEL_FLOW_URL'], 'CallType':'trans', 'TimeOut':30,
            'TimeLimit':60, 'CustomField':attempt['token']}

    def submit(self, attempt):
        submission_guard(attempt,'exotel')
        data=self._request('POST','/Calls/connect.json',data=self.payload(attempt))
        identity=data.get('Call',{}).get('Sid')
        if not identity: raise RuntimeError('Provider did not return a call identifier.')
        return str(identity),'INITIATED'

    def status(self, provider_id):
        data=self._request('GET','/Calls/'+provider_id+'.json')
        return normalize_status(data.get('Call',{}).get('Status','unknown'))


def normalize_status(value):
    return {'queued':'INITIATED','initiated':'INITIATED','connecting':'INITIATED',
        'ringing':'RINGING','in-progress':'ANSWERED','answered':'ANSWERED',
        'completed':'COMPLETED','ended':'COMPLETED','failed':'FAILED',
        'busy':'FAILED','no-answer':'FAILED','canceled':'FAILED'}.get(str(value).lower(),'UNKNOWN')


def provider_for(name):
    return {'mock':MockCallProvider,'plivo':PlivoCallProvider,'exotel':ExotelCallProvider}[name]()
