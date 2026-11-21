import json
import pytest
from fastapi import HTTPException
from backend import hermes_webhook
from backend.models import SessionLocal
from backend.work_models import WorkConnection
from backend.security import decrypt


def test_hermes_connection_is_personal_encrypted_and_allowlisted(client,owner,monkeypatch):
    body={'provider':'hermes','name':'My Hermes','token':'fixture-signing-secret-123','settings':{'url':'https://hermes.example.com/postlane'}}
    assert client.post('/api/work/connections',json=body).status_code==422
    monkeypatch.setenv('WEBHOOK_ALLOWED_ORIGINS','https://hermes.example.com')
    r=client.post('/api/work/connections',json=body);assert r.status_code==201,r.text
    text=r.text;assert 'fixture-signing-secret-123' not in text
    with SessionLocal() as db:
        c=db.get(WorkConnection,r.json()['id']);assert c.secret!=body['token'] and decrypt(c.secret)['token']==body['token']
    body['settings']['url']='http://hermes.example.com/postlane';assert client.post('/api/work/connections',json=body).status_code==422


def test_hermes_network_checks_reject_unapproved_private_dns(monkeypatch):
    monkeypatch.setenv('WEBHOOK_ALLOWED_ORIGINS','https://hermes.example.com')
    monkeypatch.setattr(hermes_webhook.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(HTTPException) as e:hermes_webhook.request('https://hermes.example.com/hook','Synthetic','fixture-secret','fixture-user')
    assert e.value.status_code==502


def test_hermes_response_contract_and_signed_request(monkeypatch):
    monkeypatch.setenv('WEBHOOK_ALLOWED_ORIGINS','https://hermes.example.com')
    monkeypatch.setattr(hermes_webhook.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
    captured={}
    class Sock:
        def settimeout(self,value):captured["timeout"]=value
        def close(self):pass
    monkeypatch.setattr(hermes_webhook.socket,'create_connection',lambda *a,**k:Sock())
    class TLS:
        def wrap_socket(self,sock,server_hostname):captured['hostname']=server_hostname;return sock
    monkeypatch.setattr(hermes_webhook.ssl,'create_default_context',lambda:TLS())
    class Reply:
        status=200
        def read(self,n):return b'{"reply":"Synthetic response","actions":[]}'
    class HTTP:
        def __init__(self,*a,**k):pass
        def request(self,method,path,body,headers):captured.update(method=method,path=path,body=body,headers=headers)
        def getresponse(self):return Reply()
        def close(self):pass
    monkeypatch.setattr(hermes_webhook.http.client,'HTTPConnection',HTTP)
    result=json.loads(hermes_webhook.request('https://hermes.example.com/hook','Synthetic','fixture-secret','fixture-user'))
    assert result['reply']=='Synthetic response'
    assert captured['headers']['Authorization']=='Bearer fixture-secret'
    assert captured['headers']['X-Postlane-Signature'].startswith('sha256=')
    assert captured['hostname']=='hermes.example.com'
    assert 'fixture-secret' not in captured['body'].decode()


def test_admin_can_approve_exact_public_origin_and_revoke_it(client,owner,monkeypatch):
    monkeypatch.delenv('WEBHOOK_ALLOWED_ORIGINS',raising=False)
    body={'provider':'hermes','name':'Own Hermes','token':'fixture-signing-secret-123','approve_origin':True,'settings':{'url':'https://hermes.example.com/postlane'}}
    r=client.post('/api/work/connections',json=body);assert r.status_code==201,r.text
    assert hermes_webhook.validate_endpoint(body['settings']['url']).hostname=='hermes.example.com'
    assert client.get('/api/work/hermes-origins').json()[0]['origin']=='https://hermes.example.com'
    assert client.post('/api/work/hermes-origins/revoke',json={'origin':'https://hermes.example.com'}).status_code==200
    with pytest.raises(HTTPException):hermes_webhook.validate_endpoint(body['settings']['url'])


def test_member_cannot_approve_new_egress_origin(client,owner,monkeypatch):
    monkeypatch.delenv('WEBHOOK_ALLOWED_ORIGINS',raising=False)
    client.post('/api/users',json={'name':'Member','email':'member@example.com','password':'fixture-member-password-123'})
    client.post('/api/auth/logout')
    response=client.post('/api/auth/login',json={'email':'member@example.com','password':'fixture-member-password-123'})
    client.headers['X-CSRF-Token']=response.json()['csrf']
    r=client.post('/api/work/connections',json={'provider':'hermes','name':'Forbidden','token':'fixture-signing-secret-123','approve_origin':True,'settings':{'url':'https://different.example.com/hook'}})
    assert r.status_code==403


def test_hermes_test_endpoint_validates_without_executing_actions(client,owner,monkeypatch):
    monkeypatch.setenv('WEBHOOK_ALLOWED_ORIGINS','https://hermes.example.com')
    r=client.post('/api/work/connections',json={'provider':'hermes','name':'Hermes','token':'fixture-signing-secret-123','settings':{'url':'https://hermes.example.com/postlane'}})
    assert r.status_code==201,r.text
    import backend.work as work
    monkeypatch.setattr(work,'generate',lambda *a:json.dumps({'reply':'Synthetic ready','actions':[]}))
    assert client.post('/api/work/connections/'+r.json()['id']+'/test').json()['ok']
    monkeypatch.setattr(work,'generate',lambda *a:json.dumps({'reply':'Synthetic wrong','actions':[{'connection_id':'unknown','operation':'create_task','arguments':{}}]}))
    assert client.post('/api/work/connections/'+r.json()['id']+'/test').status_code==502
