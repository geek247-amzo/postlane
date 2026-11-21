import json
from sqlalchemy import select
from .models import User, Domain, Mailbox, Grant, Message, Folder, now
from .security import passwords


def seed_demo(db):
    if db.scalar(select(User)):
        return
    import secrets

    user = User(
        email="alex@postlane.demo",
        name="Alex Morgan",
        role="admin",
        password_hash=passwords.hash(secrets.token_urlsafe(32)),
    )
    db.add(user)
    db.flush()
    domains = ["northstar.demo", "studiohaven.demo", "atlasventures.demo"]
    for name in domains:
        db.add(Domain(name=name, verified=False))
    specs = [
        ("alex", "Northstar", 0),
        ("hello", "Northstar", 0),
        ("finance", "Northstar", 0),
        ("support", "Northstar", 0),
        ("alex", "Studio Haven", 1),
        ("projects", "Studio Haven", 1),
        ("hello", "Studio Haven", 1),
        ("alex", "Atlas Ventures", 2),
        ("partners", "Atlas Ventures", 2),
        ("accounts", "Atlas Ventures", 2),
    ]
    boxes = []
    for i, (local, label, d) in enumerate(specs):
        b = Mailbox(
            email=f"{local}@{domains[d]}",
            name=label if local == "alex" else local.title(),
            provider="demo",
            status="demo",
            color=["#448a78", "#b185cc", "#dc9a62"][d],
            position=i,
        )
        db.add(b)
        db.flush()
        boxes.append(b)
        db.add(Grant(user_id=user.id, mailbox_id=b.id, can_write=True, can_send=True))
    for name in ["Clients", "Finance", "Projects", "Reading list"]:
        db.add(Folder(mailbox_id=boxes[0].id, name=name))
    rows = [
        (
            0,
            "Sarah Chen <sarah@example.com>",
            "The next chapter for Northstar",
            "Hi Alex,\n\nI’ve pulled together the proposal we discussed. The revised scope gives us a little more room to explore the brand direction before we lock in the launch.\n\nCould you take a look and share your thoughts on the timeline? I’m free Thursday afternoon if it’s easier to talk it through.\n\nLooking forward to building this together.\n\nSarah\nCreative Director",
            True,
            ["Clients"],
            False,
        ),
        (
            5,
            "James Wilson <james@example.com>",
            "Website refresh — ready for your review",
            "Hey Alex,\n\nThe updated layouts are ready for review. We’ve tightened up the navigation and made the project pages easier to browse.\n\nLet me know what you think before Friday’s handover.\n\nJames",
            True,
            ["Projects"],
            True,
        ),
        (
            2,
            "Nina Patel <nina@example.com>",
            "March invoice and payment schedule",
            "Hi Alex,\n\nHere is the breakdown for this month. The next payment is due on the 28th. Please confirm the billing details when you get a chance.\n\nThanks,\nNina",
            True,
            ["Finance"],
            False,
        ),
        (
            8,
            "Daniel Brooks <daniel@example.com>",
            "A quick introduction: meet the Atlas team",
            "Hi Alex,\n\nGreat catching up yesterday. I’d love to introduce you to our operations team and find a time for a short kick-off next week.\n\nWould Tuesday at 10 work?\n\nDaniel",
            False,
            ["Partners"],
            True,
        ),
        (
            0,
            "Emma Taylor <emma@example.com>",
            "Re: Let’s make Monday a little lighter",
            "Hi Alex,\n\nMonday at 9:30 works perfectly. I’ll send an agenda before the meeting so we can focus on decisions.\n\nEnjoy your weekend,\nEmma",
            False,
            [],
            False,
        ),
        (
            3,
            "Oliver Reed <oliver@example.com>",
            "Question about our onboarding",
            "Hello,\n\nWe’re getting the team set up and wanted to check if you have a short guide for adding our billing contact.\n\nAppreciate your help!\nOliver",
            True,
            ["Needs reply"],
            False,
        ),
        (
            4,
            "Studio Notes <notes@example.com>",
            "A few good things worth bookmarking",
            "This week’s reading list\n\nA thoughtful collection of design essays, independent studios, and small ideas that make a big difference.\n\nTake a little time to explore.",
            False,
            ["Reading"],
            False,
        ),
        (
            7,
            "Michael Ross <michael@example.com>",
            "Q2 planning: a first look",
            "Hi Alex,\n\nI’ve outlined the priorities for the coming quarter. The focus is on fewer projects with clearer outcomes.\n\nLet’s discuss at our next check-in.\n\nMichael",
            False,
            ["Planning"],
            False,
        ),
        (
            1,
            "Priya Shah <priya@example.com>",
            "Loved what you shared last week",
            "Alex,\n\nYour talk on running a small business really resonated. Would you be open to joining our founder roundtable next month?\n\nBest,\nPriya",
            True,
            [],
            False,
        ),
        (
            6,
            "Ben Carter <ben@example.com>",
            "Project handover confirmed",
            "Hi team,\n\nEverything is ready for Thursday. I’ve shared the final checklist with the project team.\n\nSee you there,\nBen",
            False,
            ["Projects"],
            False,
        ),
        (
            9,
            "Accounts <billing@example.com>",
            "Your monthly statement is available",
            "Hello Alex,\n\nYour statement is ready. Please review the account summary in your billing portal.\n\nThank you.",
            False,
            ["Finance"],
            False,
        ),
        (
            0,
            "Lena Ortiz <lena@example.com>",
            "Coffee next week?",
            "Hi Alex,\n\nI’ll be in town next week and would love to catch up. Are you around on Wednesday?\n\nLena",
            False,
            [],
            False,
        ),
    ]
    for i, (b, sender, subject, body, unread, labels, starred) in enumerate(rows):
        db.add(
            Message(
                mailbox_id=boxes[b].id,
                sender=sender,
                recipients=boxes[b].email,
                subject=subject,
                body=body,
                unread=unread,
                labels=json.dumps(labels),
                starred=starred,
                received_at=now() - i * 2400,
            )
        )
    db.commit()
