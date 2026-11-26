"""Share cards drawn as railroad paperwork: the train order, clearance and switching order of the exam and play pages.

A recipe module of make_share_cards.py, which lists the cards (CARDS) and runs them."""

from __future__ import annotations

import make_share_cards as kit


# ---- Achievement Program, exam and play: drawn paperwork ---------------------------------------

def ap_exam():
    """ap-exam: a Form 19 train order on its green flimsy, running Engs C and E extra from the Study Guide to the Exam.

    The order follows Standard Code Form G ("Eng 99 run extra A to F") and a Form S-C wait, the rules the deck teaches."""
    body = """<div class="desk"><div class="order">
  <div class="hd"><span class="form">19</span><div class="rr">HART RAILROAD</div><div class="kind">TRAIN ORDER No. <b class="ty">516</b></div></div>
  <div class="ln"><span>Superintendent's Office</span><span class="ty">Nov 14</span><span>20</span><span class="ty">26</span></div>
  <div class="ln"><span>To</span><span class="ty wide">C &amp; E Extra East</span><span>At</span><span class="ty wide">Study Guide</span><span>Opr.</span><span class="ty">HT</span></div>
  <div class="body ty">Engs C and E run extra Study Guide to Exam<br>and wait at Flashcards until learned.</div>
  <div class="copy">CONDUCTOR AND ENGINEMAN MUST EACH HAVE A COPY OF THIS ORDER</div>
  <div class="ln foot"><span>Repeated at</span><span class="ty">8 10 pm</span><span>Made</span><span class="ty">Complete</span><span>Time</span><span class="ty">8 15 pm</span><span>Opr.</span><span class="ty">HT</span></div>
  <div class="stamp">OK<br><small>8 15 PM</small></div>
</div></div>"""
    style = """@import url("https://fonts.googleapis.com/css2?family=Special+Elite&display=swap");
body{background:#0c2f39}
.desk{width:1200px;height:630px;display:grid;place-items:center;
  background:radial-gradient(ellipse at 30% 20%,#164c5a 0,#0c2f39 60%,#081f27 100%)}
.order{position:relative;width:1010px;padding:30px 46px 28px;transform:rotate(-1.6deg);
  background:linear-gradient(180deg,#e6efd2,#dbe7c3);color:#26331f;
  font-family:"Source Serif 4",Georgia,serif;box-shadow:0 22px 50px rgba(0,0,0,.45),0 2px 0 rgba(255,255,255,.4) inset}
.order::after{content:"";position:absolute;inset:0;pointer-events:none;
  background:repeating-linear-gradient(0deg,rgba(60,80,40,.05) 0 1px,transparent 1px 4px)}
.hd{display:flex;flex-direction:column;align-items:center;gap:2px;border-bottom:2px solid #3d4d33;padding-bottom:10px;position:relative}
.form{position:absolute;left:0;top:0;font:700 46px/1 "Barlow Condensed",sans-serif;border:3px solid #3d4d33;padding:2px 10px}
.rr{font:700 44px/1 "Barlow Condensed",sans-serif;letter-spacing:.14em}
.kind{font-size:22px;letter-spacing:.2em}
.ty{font-family:"Special Elite","Courier New",monospace;color:#1d2b5c;letter-spacing:0;font-weight:400}
.kind .ty{font-size:28px;padding:0 8px}
.ln{display:flex;align-items:baseline;gap:10px;font-size:19px;margin-top:14px}
.ln .ty{font-size:24px;border-bottom:1.5px solid #4c5d40;padding:0 10px 1px;min-width:60px}
.ln .wide{flex:1}
.body{font-size:34px;line-height:52px;margin:24px 0 18px;padding:2px 4px;
  background:repeating-linear-gradient(180deg,transparent 0 50px,#9fb08a 50px 52px)}
.copy{font-size:15px;letter-spacing:.12em;text-align:center;border-top:1px solid #4c5d40;padding-top:8px}
.foot{font-size:16px}.foot .ty{font-size:21px}
.stamp{position:absolute;right:52px;bottom:18px;transform:rotate(-10deg);color:rgba(178,36,36,.82);
  border:4px solid rgba(178,36,36,.75);border-radius:8px;padding:4px 18px;text-align:center;
  font:700 48px/0.95 "Barlow Condensed",sans-serif;letter-spacing:.06em}
.stamp small{font-size:22px;letter-spacing:.1em}
"""
    return kit.card(kit.draw("ap-exam", body, style))


def ap_exam_run():
    """ap-exam-run: a Clearance Form A on the Kestrel Valley, clearing Extra 812 East at Ashby with two orders, stamped Extra East.

    The form follows Standard Code Rule 211: the number of orders and the number of each, then OK, the time and the dispatcher's initials."""
    body = """<div class="desk"><div class="form">
  <div class="hd"><div class="rr">KESTREL VALLEY RAILROAD</div><div class="kind">CLEARANCE FORM A</div></div>
  <div class="ln"><span>Station</span><span class="ty wide">Ashby</span><span class="ty">Nov 16</span><span>19</span><span class="ty">49</span></div>
  <div class="ln"><span>To</span><span class="ty wide">Extra 812 East</span></div>
  <div class="body"><span>I have</span><span class="ty">2</span><span>orders for your train. Nos</span><span class="ty wide">14, 15</span></div>
  <div class="ln foot"><span>OK</span><span class="ty">6 14 am</span><span>Dispatcher</span><span class="ty">RK</span><span>Opr.</span><span class="ty">HT</span></div>
  <div class="copy">CONDUCTOR, ENGINEMAN AND FIREMAN MUST SEE THAT THIS CLEARANCE AGREES WITH THEIR ORDERS</div>
  <div class="stamp">EXTRA<br>EAST</div>
</div></div>"""
    style = """@import url("https://fonts.googleapis.com/css2?family=Special+Elite&display=swap");
body{background:#2c2418}
.desk{width:1200px;height:630px;display:grid;place-items:center;
  background:radial-gradient(ellipse at 30% 20%,#5a4a32 0,#3a2f20 60%,#241d14 100%)}
.form{position:relative;width:980px;padding:30px 46px 26px;transform:rotate(1.4deg);
  background:linear-gradient(180deg,#f7f3e6,#ece5cf);color:#1d2733;
  font-family:"Source Serif 4",Georgia,serif;box-shadow:0 22px 50px rgba(0,0,0,.5)}
.hd{display:flex;flex-direction:column;align-items:center;gap:4px;border-bottom:2px solid #1d2733;padding-bottom:10px}
.rr{font:700 46px/1 "Barlow Condensed",sans-serif;letter-spacing:.14em}
.kind{font:600 26px/1 "Barlow Condensed",sans-serif;letter-spacing:.3em}
.ty{font-family:"Special Elite","Courier New",monospace;color:#2c4a86;border-bottom:1.5px solid #5d5a4e;padding:0 12px 1px;min-width:60px}
.ln,.body{display:flex;align-items:baseline;gap:12px;font-size:21px;margin-top:20px}
.ln .ty{font-size:28px}.wide{flex:1}
.body{font-size:30px;margin:34px 0 22px}.body .ty{font-size:38px}
.foot .ty{font-size:26px}
.copy{font-size:14px;letter-spacing:.1em;text-align:center;border-top:1px solid #5d5a4e;padding-top:10px;margin-top:22px}
.stamp{position:absolute;right:70px;bottom:62px;transform:rotate(-12deg);color:rgba(163,48,43,.85);
  border:5px solid rgba(163,48,43,.8);border-radius:8px;padding:6px 18px;text-align:center;
  font:700 52px/0.92 "Barlow Condensed",sans-serif;letter-spacing:.08em}
"""
    return kit.card(kit.draw("ap-exam-run", body, style))


def play_neville():
    """play-neville: the game's switching orders for #105 on the P&OV, with the game's logo, stamped Extra East, on a desk lit like the coke works at dusk.

    Drawn in the manner of ap-exam-run; the P&OV's own form is not known, so the layout is the game's switch list on paper."""
    body = f"""<div class="desk"><div class="form">
  <div class="hd"><img src="{kit._site}play/neville.svg" alt=""><div><div class="rr">PITTSBURGH &amp; OHIO VALLEY</div><div class="kind">SWITCHING ORDERS · NEVILLE ISLAND</div></div></div>
  <div class="ln"><span>Job</span><span class="ty">#105</span><span>Engine</span><span class="ty">SW9 #4</span><span>Date</span><span class="ty wide">1981</span></div>
  <ol class="work">
    <li><span class="ty">2 ore drags to the car dumper</span></li>
    <li><span class="ty">Fuel #4 between trips</span></li>
    <li><span class="ty">Tie up West Yard, 3:30</span></li>
  </ol>
  <div class="ln foot"><span>Trainmaster</span><span class="ty wide">&nbsp;</span><span>On duty</span><span class="ty">7 00 am</span></div>
  <div class="stamp">EXTRA EAST<small>HART RAILROAD</small></div>
</div></div>"""
    style = """@import url("https://fonts.googleapis.com/css2?family=Special+Elite&display=swap");
body{background:#1f1d24}
.desk{width:1200px;height:630px;display:grid;place-items:center;
  background:radial-gradient(ellipse at 75% 105%,rgba(232,145,58,.55) 0,rgba(181,87,58,.25) 30%,transparent 60%),
  linear-gradient(180deg,#2c2142 0,#4a2a48 45%,#26232b 100%)}
.form{position:relative;width:960px;padding:26px 44px 26px;transform:rotate(-1.2deg);
  background:linear-gradient(180deg,#f1f3f6,#dfe3e9);color:#1c1b22;
  font-family:"Source Serif 4",Georgia,serif;box-shadow:0 22px 50px rgba(0,0,0,.55)}
.hd{display:flex;align-items:center;gap:22px;border-bottom:2px solid #1c1b22;padding-bottom:12px}
.hd img{width:92px;height:92px}
.rr{font:700 50px/1 "Barlow Condensed",sans-serif;letter-spacing:.1em}
.kind{font:600 24px/1.2 "Barlow Condensed",sans-serif;letter-spacing:.24em;color:#a4472b;margin-top:6px}
.ty{font-family:"Special Elite","Courier New",monospace;color:#2f4a6b;border-bottom:1.5px solid #545b67;padding:0 12px 1px;min-width:60px}
.ln{display:flex;align-items:baseline;gap:12px;font-size:21px;margin-top:20px}
.ln .ty{font-size:27px}.wide{flex:1}
.work{margin:22px 0 4px;padding-left:34px;font-size:22px;display:flex;flex-direction:column;gap:12px}
.work .ty{font-size:29px;border-bottom:none;padding:0}
.foot .ty{font-size:25px}
.stamp{position:absolute;right:56px;bottom:72px;transform:rotate(-10deg);color:rgba(164,71,43,.88);
  border:5px solid rgba(164,71,43,.82);border-radius:8px;padding:8px 20px 6px;text-align:center;
  font:700 54px/0.95 "Barlow Condensed",sans-serif;letter-spacing:.08em}
.stamp small{display:block;font-size:24px;letter-spacing:.22em;margin-top:4px}
"""
    return kit.card(kit.draw("play-neville", body, style))
