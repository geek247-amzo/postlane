import json
from sqlalchemy import select
from backend.models import SessionLocal, Mailbox, Message, Grant, User, ApiKey, Draft, AgentDraftAuthority, now
from backend.security import encrypt, draft_hash
from backend import worker


def key(client, mailbox, name='Agent', scopes=None):
    r=client.post('/api/keys',json={'name':name,'scopes':scopes or ['messages:read','messages:write','drafts:write','mail:send'],'mailbox_ids':[mailbox['id']]})
    assert r.status_code==201,r.text
    return r.json(), {'Authorization':'Bearer '+r.json()['token']}


def connected(mailbox):
    with SessionLocal() as db:
        b=db.get(Mailbox,mailbox['id']);b.config=encrypt({'imap_host':'mail.example.com','smtp_host':'mail.example.com','password':'fixture-only'});db.commit()


def test_categories_filter_without_granting_access(client, mailbox):
    with SessionLocal() as db:
        owner=db.scalar(select(User).where(User.email=='owner@example.com'))
        shared=Mailbox(email='team@example.com',name='Team',provider='imap',management_mode='shared')
        ai=Mailbox(email='agent@example.com',name='Agent',provider='imap',management_mode='ai')
        hidden=Mailbox(email='hidden@example.com',name='Hidden',provider='imap',management_mode='ai')
        db.add_all([shared,ai,hidden]);db.flush()
        for b in [shared,ai]:
            db.add(Grant(user_id=owner.id,mailbox_id=b.id));db.add(Message(mailbox_id=b.id,sender='fixture@example.com',recipients=b.email,subject=b.name,body='Synthetic'))
        db.add(Message(mailbox_id=hidden.id,sender='fixture@example.com',recipients=hidden.email,subject='Hidden',body='Synthetic'));db.commit()
    assert client.get('/api/messages?management_mode=human').json()['total']==2
    assert client.get('/api/messages?management_mode=shared').json()['total']==1
    assert client.get('/api/messages?management_mode=ai').json()['total']==1
    assert client.get('/api/messages?management_mode=all').json()['total']==3
    assert client.get('/api/messages?management_mode=owner').status_code==422


def test_ai_send_needs_explicit_opt_in_and_rechecks_key(client, mailbox,monkeypatch):
    connected(mailbox)
    r=client.patch('/api/mailboxes/'+mailbox['id'],json={'management_mode':'ai'})
    assert r.status_code==200 and not r.json()['ai_send_enabled']
    k,h=key(client,mailbox)
    body={'to':'recipient@example.com','subject':'Synthetic','body':'Synthetic test'}
    assert client.post('/api/mailboxes/'+mailbox['id']+'/send',json=body,headers=h).status_code==403
    assert client.patch('/api/mailboxes/'+mailbox['id'],json={'ai_send_enabled':True}).status_code==200
    sent=client.post('/api/mailboxes/'+mailbox['id']+'/send',json=body,headers=h)
    assert sent.status_code==202,sent.text
    with SessionLocal() as db:
        d=db.get(Draft,sent.json()['id']);d.scheduled_at=now()-1;db.commit()
    assert client.delete('/api/keys/'+k['id']).status_code==200
    calls=[];monkeypatch.setattr(worker,'send_message',lambda *a:calls.append(a))
    worker.run_submissions()
    assert not calls
    with SessionLocal() as db:assert db.get(Draft,sent.json()['id']).status!='sent'


def test_ai_authorized_api_submission_reaches_mock_provider(client,mailbox,monkeypatch):
    connected(mailbox)
    client.patch('/api/mailboxes/'+mailbox['id'],json={'management_mode':'ai','ai_send_enabled':True})
    _,h=key(client,mailbox)
    sent=client.post('/api/mailboxes/'+mailbox['id']+'/send',headers=h,json={'to':'recipient@example.com','subject':'Synthetic','body':'Synthetic'})
    assert sent.status_code==202,sent.text
    with SessionLocal() as db:d=db.get(Draft,sent.json()['id']);d.scheduled_at=now()-1;db.commit()
    calls=[];monkeypatch.setattr(worker,'send_message',lambda *a:calls.append(a))
    worker.run_submissions();assert len(calls)==1
    with SessionLocal() as db:assert db.get(Draft,sent.json()['id']).status=='sent'


def test_agents_cannot_read_or_edit_another_keys_draft(client,mailbox):
    _,a=key(client,mailbox,'First');_,b=key(client,mailbox,'Second')
    d=client.post('/api/drafts',headers=a,json={'mailbox_id':mailbox['id'],'to':'recipient@example.com','subject':'Synthetic','body':'Synthetic'}).json()
    assert not client.get('/api/drafts',headers=b).json()
    assert client.put('/api/drafts/'+d['id'],headers=b,json={'mailbox_id':mailbox['id'],'to':'recipient@example.com','subject':'Changed','body':'Changed','version':d['version']}).status_code==404


def test_shared_user_creation_grants_exact_rights_atomically(client,mailbox):
    client.patch('/api/mailboxes/'+mailbox['id'],json={'management_mode':'shared'})
    for n,write,send in [('Reader',False,False),('Sender',True,True)]:
        r=client.post('/api/users',json={'name':n,'email':n.lower()+'@example.com','password':'fixture-password-with-length','grants':[{'mailbox_id':mailbox['id'],'can_write':write,'can_send':send}]})
        assert r.status_code==201,r.text
        with SessionLocal() as db:
            g=db.scalar(select(Grant).where(Grant.user_id==r.json()['id']));assert (g.can_write,g.can_send)==(write,send)
    r=client.post('/api/users',json={'name':'No partial','email':'partial@example.com','password':'fixture-password-with-length','grants':[{'mailbox_id':'missing'}]})
    assert r.status_code==404
    with SessionLocal() as db:assert not db.scalar(select(User).where(User.email=='partial@example.com'))


def test_member_cannot_change_management_or_autonomy(client,mailbox):
    r=client.post('/api/users',json={'name':'Member','email':'member@example.com','password':'fixture-password-with-length','grants':[{'mailbox_id':mailbox['id'],'can_write':True}]})
    client.post('/api/auth/logout')
    login=client.post('/api/auth/login',json={'email':'member@example.com','password':'fixture-password-with-length'}).json();client.headers['X-CSRF-Token']=login['csrf']
    assert client.patch('/api/mailboxes/'+mailbox['id'],json={'management_mode':'ai','ai_send_enabled':True}).status_code==403
    assert client.post('/api/keys',json={'name':'Forbidden send','scopes':['mail:send'],'mailbox_ids':[mailbox['id']]}).status_code==403


def test_human_and_shared_boxes_cannot_send_directly_by_api(client,mailbox):
    connected(mailbox)
    _,h=key(client,mailbox)
    for mode in ['human','shared']:
        assert client.patch('/api/mailboxes/'+mailbox['id'],json={'management_mode':mode}).status_code==200
        assert client.post('/api/mailboxes/'+mailbox['id']+'/send',headers=h,json={'to':'recipient@example.com','subject':'Synthetic','body':'Synthetic'}).status_code==403
    assert client.patch('/api/mailboxes/'+mailbox['id'],json={'ai_send_enabled':True}).status_code==422


def test_turning_off_ai_sending_cancels_queued_authority(client,mailbox,monkeypatch):
    connected(mailbox)
    client.patch('/api/mailboxes/'+mailbox['id'],json={'management_mode':'ai','ai_send_enabled':True})
    _,h=key(client,mailbox)
    sent=client.post('/api/mailboxes/'+mailbox['id']+'/send',headers=h,json={'to':'recipient@example.com','subject':'Synthetic','body':'Synthetic'})
    assert sent.status_code==202
    client.patch('/api/mailboxes/'+mailbox['id'],json={'ai_send_enabled':False})
    with SessionLocal() as db:d=db.get(Draft,sent.json()['id']);d.scheduled_at=now()-1;db.commit()
    calls=[];monkeypatch.setattr(worker,'send_message',lambda *a:calls.append(a))
    worker.run_submissions();assert not calls


def test_additive_migration_keeps_existing_boxes_human_and_is_repeatable():
    from sqlalchemy import create_engine,text,inspect
    from backend.mailbox_modes import migrate
    engine=create_engine('sqlite://')
    with engine.begin() as c:
        c.execute(text('CREATE TABLE mailboxes (id VARCHAR(32) PRIMARY KEY, email VARCHAR(320))'))
        c.execute(text("INSERT INTO mailboxes (id,email) VALUES ('fixture','fixture@example.com')"))
    migrate(engine);migrate(engine)
    with engine.connect() as c:
        row=c.execute(text('SELECT management_mode,ai_send_enabled FROM mailboxes')).one()
        assert row[0]=='human' and not row[1]
    engine.dispose()


def test_existing_database_upgrade_preserves_mailbox_and_grants(client,mailbox):
    from backend.models import engine
    from sqlalchemy import text
    from backend.mailbox_modes import migrate
    with engine.begin() as c:
        before=c.execute(text('SELECT COUNT(*) FROM grants')).scalar()
        c.execute(text('ALTER TABLE mailboxes DROP COLUMN ai_send_enabled'))
        c.execute(text('ALTER TABLE mailboxes DROP COLUMN management_mode'))
    migrate(engine);migrate(engine)
    with engine.connect() as c:
        row=c.execute(text('SELECT management_mode,ai_send_enabled FROM mailboxes WHERE id=:id'),{'id':mailbox['id']}).one()
        assert row[0]=='human' and not row[1]
        assert c.execute(text('SELECT COUNT(*) FROM grants')).scalar()==before
        # Old application projections continue to work after this additive upgrade.
        assert c.execute(text('SELECT id,email,provider FROM mailboxes WHERE id=:id'),{'id':mailbox['id']}).one()[0]==mailbox['id']
