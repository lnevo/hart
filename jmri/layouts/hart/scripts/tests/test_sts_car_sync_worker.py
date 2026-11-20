"""sts_car_sync.py's Jython half: the memory listener and the worker thread that JMRI starts.

test_sts_car_sync.py covers the planning logic. This file runs `_start()` against stand-ins
for Java and JMRI and pins what the thread does today: one reply per request, a failed
fetch or bad data answered instead of dropped, and which failures end the thread.

No thread runs here. The fake `java.lang.Thread` only keeps the worker function, and the
fake queue raises `Drained` when it is empty, so a test runs the loop on its own thread
until the jobs are used up.

Java exceptions are modelled on Jython 2.7.4 (checked against JMRI's jython-standalone jar,
2026-11-19): `except Exception` does not catch a Java exception, `except java.lang.Exception`
does not catch a Python exception or a `java.lang.Error`, and an uncaught Python exception
ends a `java.lang.Thread`. So the fakes derive from BaseException, outside Exception.

`runOnGUI` is modelled on stock JMRI 5.16 (java/src/jmri/util/ThreadingUtil.java): called off
the GUI thread, as the worker calls it, it runs the function with `invokeAndWait`, logs
whatever the function throws and returns normally. The worker never sees that failure.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jmri_fake as jf  # noqa: E402
import test_sts_car_sync as base  # noqa: E402  (the railroad fixtures and the loaded script)

sync = base.sync


class Drained(BaseException):
    """The fake queue is empty: where the real worker would block in take()."""


class JavaThrowable(BaseException):
    pass


class JavaException(JavaThrowable):
    """java.lang.Exception: not a Python Exception in Jython."""


class JavaError(JavaThrowable):
    """java.lang.Error (StackOverflowError, NoClassDefFoundError...): not a java.lang.Exception."""


class Queue:
    made = []

    def __init__(self):
        self.items = []
        Queue.made.append(self)

    def put(self, item):
        self.items.append(item)

    def take(self):
        if not self.items:
            raise Drained()
        return self.items.pop(0)


class Thread:
    made = []

    def __init__(self, target):
        self.target, self.name, self.daemon, self.starts = target, None, None, 0
        Thread.made.append(self)

    def setName(self, name):
        self.name = name

    def setDaemon(self, value):
        self.daemon = value

    def start(self):
        self.starts += 1


class Jmri:
    """The fake JMRI one test sees: memories, the four Operations managers, the GUI hook, save."""

    def __init__(self):
        self.memories = jf.MemoryManager(jf.FakeMemory)
        self.rr = base.railroad()[0]
        self.events = []          # "gui" and "save", in the order the worker made them
        self.fetches = []         # the manager class names asked of InstanceManager
        self.fetch_error = None   # raised by the Operations manager lookups when set
        self.gui_errors = []      # what runOnGUI logged instead of throwing
        self.replies = []

    def get_default(self, cls):
        name = cls.__name__
        if name == "MemoryManager":
            return self.memories
        self.fetches.append(name)
        if self.fetch_error is not None:
            raise self.fetch_error
        return {"CarManager": self.rr.cars, "LocationManager": self.rr.locations,
                "CarLoads": self.rr.loads, "CarTypes": self.rr.types}[name]

    def run_on_gui(self, function):
        """Stock ThreadingUtil.runOnGUI off the GUI thread: a failure in `function` is logged
        ("Error while on GUI thread"), not thrown to the caller."""
        self.events.append("gui")
        try:
            function()
        except (Exception, JavaThrowable) as exc:
            self.gui_errors.append(exc)

    def save(self):
        self.events.append("save")

    def modules(self):
        def mod(name, **attrs):
            m = types.ModuleType(name)
            m.__dict__.update(attrs)
            return m

        def cls(name):
            return type(name, (object,), {})

        lang = mod("java.lang", Thread=Thread, Throwable=JavaThrowable, Exception=JavaException,
                   Error=JavaError)
        beans = mod("java.beans", PropertyChangeListener=cls("PropertyChangeListener"))
        concurrent = mod("java.util.concurrent", LinkedBlockingQueue=Queue)
        util = mod("java.util", concurrent=concurrent)
        java = mod("java", lang=lang, beans=beans, util=util)
        locations = mod("jmri.jmrit.operations.locations", LocationManager=cls("LocationManager"))
        cars = mod("jmri.jmrit.operations.rollingstock.cars", CarLoads=cls("CarLoads"),
                   CarManager=cls("CarManager"), CarTypes=cls("CarTypes"))
        stock = mod("jmri.jmrit.operations.rollingstock", cars=cars)
        operations = mod("jmri.jmrit.operations", OperationsXml=types.SimpleNamespace(save=self.save),
                         locations=locations, rollingstock=stock)
        jmrit = mod("jmri.jmrit", operations=operations)
        jmri_util = mod("jmri.util", ThreadingUtil=types.SimpleNamespace(runOnGUI=self.run_on_gui))
        jmri = mod("jmri", InstanceManager=types.SimpleNamespace(getDefault=self.get_default),
                   MemoryManager=cls("MemoryManager"), jmrit=jmrit, util=jmri_util)
        return {"java": java, "java.lang": lang, "java.beans": beans, "java.util": util,
                "java.util.concurrent": concurrent, "jmri": jmri, "jmri.jmrit": jmrit,
                "jmri.jmrit.operations": operations, "jmri.jmrit.operations.locations": locations,
                "jmri.jmrit.operations.rollingstock": stock,
                "jmri.jmrit.operations.rollingstock.cars": cars, "jmri.util": jmri_util}


class Recorder:
    """A listener on the reply Memory: every reply the worker set, in order."""

    def __init__(self, into):
        self.into = into

    def propertyChange(self, event):
        self.into.append(json.loads(event.getNewValue()))


def batch(id_, **car):
    return json.dumps({"id": id_, "cars": [dict({"car": "BO8476"}, **car)]})


class Worker(unittest.TestCase):
    def setUp(self):
        Queue.made, Thread.made = [], []
        self.jmri = Jmri()
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(jf.fake_modules(self.jmri.modules()))
        stack.enter_context(jf.no_network())
        self.out = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        sync._start()
        self.request = self.jmri.memories.getMemory(sync.REQUEST)
        self.reply = self.jmri.memories.getMemory(sync.REPLY)
        self.reply.addPropertyChangeListener(Recorder(self.jmri.replies))

    def run_worker(self, thread=None):
        """Run the worker loop until its queue is empty, as the thread would."""
        with self.assertRaises(Drained):
            (thread or Thread.made[-1]).target()

    def car(self, car_id="BO8476"):
        return self.jmri.rr.cars.getById(car_id)

    # --- start-up -------------------------------------------------------------------

    def test_start_makes_the_memories_one_listener_and_one_daemon_thread(self):
        memories = self.jmri.memories
        self.assertEqual(sorted(memories.beans), sorted([sync.REQUEST, sync.REPLY, sync.READY]))
        self.assertEqual(memories.getMemory(sync.READY).getValue(), sync.VERSION)
        self.assertIsNone(self.reply.getValue())
        self.assertEqual(len(self.request.getPropertyChangeListeners()), 1)
        self.assertEqual(len(Thread.made), 1)
        thread = Thread.made[0]
        self.assertEqual((thread.name, thread.daemon, thread.starts), ("STS car sync", True, 1))
        self.assertEqual(self.out.getvalue(), "sts_car_sync listening on %s\n" % sync.REQUEST)

    def test_start_does_not_read_operations_or_touch_the_gui(self):
        self.assertEqual(self.jmri.fetches, [])
        self.assertEqual(self.jmri.events, [])

    def test_script_only_starts_itself_under_jython(self):
        # plain Python is the tests: loading the file must not need Java
        self.assertFalse(sys.platform.startswith("java"))
        self.assertIn('if sys.platform.startswith("java"):', base.SCRIPT.read_text(encoding="utf-8"))

    # --- the listener, on JMRI's thread -----------------------------------------------

    def test_a_request_is_only_queued_on_the_thread_that_set_the_memory(self):
        self.request.setValue(batch("q1", load="Steel"))
        self.assertEqual(Queue.made[0].items, [batch("q1", load="Steel")])
        self.assertIsInstance(Queue.made[0].items[0], str)
        self.assertEqual(self.jmri.fetches, [])       # no Operations lookup,
        self.assertEqual(self.jmri.events, [])        # no GUI call, no save,
        self.assertEqual(self.jmri.replies, [])       # and no reply until the worker runs
        self.assertEqual(self.car().load, "E")

    def test_listener_ignores_other_properties_and_empty_values(self):
        listener = self.request.getPropertyChangeListeners()[0]
        listener.propertyChange(jf._ValueEvent("comment", None, batch("x")))
        listener.propertyChange(jf._ValueEvent("value", "old", None))
        listener.propertyChange(jf._ValueEvent("value", "old", ""))
        self.assertEqual(Queue.made[0].items, [])

    # --- one pass -------------------------------------------------------------------

    def test_a_pass_applies_on_the_gui_thread_then_saves_then_replies(self):
        self.request.setValue(batch("p1", load="Steel"))
        self.run_worker()
        self.assertEqual(self.car().load, "Steel")
        self.assertEqual(self.jmri.events, ["gui", "save"])   # save runs on the worker, after the GUI call
        self.assertEqual(len(self.jmri.replies), 1)
        out = self.jmri.replies[0]
        self.assertEqual((out["id"], out["ok"], out["saved"], out["summary"]), ("p1", True, True, {"changed": 1}))
        self.assertEqual(self.reply.getValue(), json.dumps(out))

    def test_a_pass_fetches_the_four_managers_afresh(self):
        for n in ("f1", "f2"):
            self.request.setValue(batch(n))
        self.run_worker()
        self.assertEqual(self.jmri.fetches, ["CarManager", "LocationManager", "CarLoads", "CarTypes"] * 2)

    def test_a_pass_with_nothing_to_change_or_a_dry_run_makes_no_gui_call_and_no_save(self):
        self.request.setValue(batch("n1"))
        self.request.setValue(json.dumps({"id": "n2", "dry_run": True, "cars": [{"car": "BO8476", "load": "Steel"}]}))
        self.run_worker()
        self.assertEqual(self.jmri.events, [])
        self.assertEqual(self.car().load, "E")
        self.assertEqual([(r["id"], r["saved"]) for r in self.jmri.replies], [("n1", False), ("n2", False)])
        self.assertEqual(self.jmri.replies[1]["summary"], {"changed": 1})

    def test_save_false_applies_without_saving(self):
        self.request.setValue(json.dumps({"id": "s1", "save": False, "cars": [{"car": "BO8476", "load": "Steel"}]}))
        self.run_worker()
        self.assertEqual(self.jmri.events, ["gui"])
        self.assertFalse(self.jmri.replies[0]["saved"])

    def test_names_command_is_answered_without_gui_or_save(self):
        self.request.setValue(json.dumps({"id": "nm", "command": "names"}))
        self.run_worker()
        out = self.jmri.replies[0]
        self.assertEqual((out["id"], out["ok"], out["empty"]), ("nm", True, "E"))
        self.assertEqual(self.jmri.events, [])

    def test_requests_are_answered_in_order_one_reply_each(self):
        for n, load in (("o1", "Steel"), ("o2", "E"), ("o3", "Steel")):
            self.request.setValue(batch(n, load=load))
        self.run_worker()
        self.assertEqual([r["id"] for r in self.jmri.replies], ["o1", "o2", "o3"])
        self.assertEqual(self.car().load, "Steel")

    # --- bad data: answered, and the loop goes on -------------------------------------

    def test_bad_json_is_answered_with_an_error_and_the_next_request_still_runs(self):
        self.request.setValue("{not json")
        self.request.setValue(batch("after", load="Steel"))
        self.run_worker()
        bad, good = self.jmri.replies
        self.assertEqual((bad["id"], bad["ok"]), (None, False))
        self.assertTrue(bad["error"])
        self.assertEqual((good["id"], good["ok"]), ("after", True))
        self.assertEqual(self.car().load, "Steel")

    def test_json_that_is_not_an_object_is_answered_with_an_error(self):
        for text in ("[1, 2]", "7", '"text"'):
            self.request.setValue(text)
        self.request.setValue(batch("after"))
        self.run_worker()
        self.assertEqual([(r["id"], r["ok"]) for r in self.jmri.replies],
                         [(None, False)] * 3 + [("after", True)])
        self.assertEqual(self.jmri.events, [])

    def test_cars_that_is_not_a_list_of_objects_fails_the_batch_but_keeps_its_id(self):
        self.request.setValue(json.dumps({"id": "c1", "cars": ["BO8476"]}))
        self.request.setValue(json.dumps({"id": "c2", "cars": 5}))
        self.request.setValue(batch("after"))
        self.run_worker()
        self.assertEqual([(r["id"], r["ok"]) for r in self.jmri.replies],
                         [("c1", False), ("c2", False), ("after", True)])

    def test_a_python_error_in_one_car_is_reported_and_the_other_cars_still_change(self):
        def refuse(location, track):
            raise ValueError("bad car record")
        self.car("UTLX1").testLocation = refuse
        self.request.setValue(json.dumps({"id": "m1", "cars": [
            {"car": "UTLX1", "location": "Ferrellgas"}, {"car": "BO8476", "load": "Steel"}]}))
        self.run_worker()
        out = self.jmri.replies[0]
        self.assertEqual((out["id"], out["ok"], out["summary"]), ("m1", True, {"error": 1, "changed": 1}))
        self.assertEqual(out["cars"][0]["reason"], "bad car record")
        self.assertEqual(self.car().load, "Steel")
        self.assertEqual(self.jmri.events, ["gui", "save"])

    # --- Java exceptions: answered without the request's id ---------------------------

    def test_a_failed_fetch_is_answered_without_an_id_and_the_next_request_still_runs(self):
        """Fault, not fixed here: the error reply has no "id", so STS cannot match it to its request."""
        self.jmri.fetch_error = JavaException("no CarManager")
        self.request.setValue(batch("j1", load="Steel"))
        self.run_worker()
        self.assertEqual(self.jmri.replies, [{"ok": False, "error": "no CarManager"}])
        self.assertEqual(self.jmri.fetches, ["CarManager"])
        self.jmri.fetch_error = None
        self.request.setValue(batch("after", load="Steel"))
        self.run_worker()
        self.assertEqual((self.jmri.replies[1]["id"], self.jmri.replies[1]["ok"]), ("after", True))

    def test_a_java_exception_in_one_car_fails_the_whole_batch_without_an_id(self):
        """Fault, not fixed here: run_batch's `except Exception` ("one bad car must not stop the
        rest") does not catch a Java exception in Jython, so no car in the batch changes."""
        def refuse(location, track):
            raise JavaException("NullPointerException")
        self.car("UTLX1").testLocation = refuse
        self.request.setValue(json.dumps({"id": "j2", "cars": [
            {"car": "BO8476", "load": "Steel"}, {"car": "UTLX1", "location": "Ferrellgas"}]}))
        self.request.setValue(batch("after"))
        self.run_worker()
        self.assertEqual(self.jmri.replies[0], {"ok": False, "error": "NullPointerException"})
        self.assertEqual(self.car().load, "E")
        self.assertEqual(self.jmri.events, [])
        self.assertEqual(self.jmri.replies[1]["id"], "after")

    # --- a failure while applying, on the GUI thread: logged by JMRI, never seen here ----

    def test_a_python_error_while_applying_is_swallowed_and_the_reply_says_saved(self):
        """Known fault, not fixed here: stock runOnGUI logs the failure and returns, so the
        worker saves and answers ok/saved/changed for a car that did not change."""
        def refuse(load):
            raise ValueError("cannot set load")
        self.car().setLoadName = refuse
        self.request.setValue(batch("a1", load="Steel"))
        self.request.setValue(batch("after"))
        self.run_worker()
        first, after = self.jmri.replies
        self.assertEqual((first["id"], first["ok"], first["saved"], first["summary"]),
                         ("a1", True, True, {"changed": 1}))
        self.assertNotIn("error", first)
        self.assertEqual(self.car().load, "E")                      # the reply is wrong
        self.assertEqual(self.jmri.events, ["gui", "save"])
        self.assertEqual([str(e) for e in self.jmri.gui_errors], ["cannot set load"])
        self.assertEqual((after["id"], after["ok"]), ("after", True))

    def test_a_java_exception_while_applying_is_swallowed_and_the_reply_says_saved(self):
        """Known fault, not fixed here: the cars before the failure change, the failing car and
        every car after it do not, and the reply still says ok, saved and all of them changed."""
        def refuse(location, track, force):
            raise JavaException("setLocation failed")
        self.car("UTLX1").setLocation = refuse
        self.request.setValue(json.dumps({"id": "j3", "cars": [
            {"car": "BO8476", "load": "Steel"}, {"car": "UTLX1", "location": "Ferrellgas"},
            {"car": "BO8476", "load": "E"}]}))
        self.run_worker()
        out = self.jmri.replies[0]
        self.assertEqual((out["id"], out["ok"], out["saved"]), ("j3", True, True))
        self.assertEqual([c["status"] for c in out["cars"]], ["changed", "changed", "unchanged"])
        self.assertEqual(self.car().load, "Steel")                  # applied before the failure
        self.assertEqual(self.jmri.events, ["gui", "save"])         # saved half applied
        self.assertEqual([str(e) for e in self.jmri.gui_errors], ["setLocation failed"])

    @unittest.expectedFailure
    def test_wanted_a_failure_while_applying_is_not_answered_as_ok(self):
        """What the reply should say; fails today (see the two tests above)."""
        def refuse(load):
            raise ValueError("cannot set load")
        self.car().setLoadName = refuse
        self.request.setValue(batch("w0", load="Steel"))
        self.run_worker()
        self.assertFalse(self.jmri.replies[0]["ok"])

    # --- what ends the thread ---------------------------------------------------------

    def test_a_java_error_ends_the_thread_with_no_reply(self):
        """Fault, not fixed here: `except java.lang.Exception` lets a java.lang.Error through."""
        self.jmri.fetch_error = JavaError("StackOverflowError")
        self.request.setValue(batch("e1"))
        self.request.setValue(batch("never"))
        with self.assertRaises(JavaError):
            Thread.made[0].target()
        self.assertEqual(self.jmri.replies, [])
        self.assertEqual(Queue.made[0].items, [batch("never")])     # left waiting; nothing takes it

    def test_a_python_error_outside_answer_ends_the_thread_with_no_reply(self):
        """Fault, not fixed here: only Java exceptions are caught around the fetch."""
        self.jmri.fetch_error = TypeError("manager lookup broke")
        self.request.setValue(batch("e2"))
        self.request.setValue(batch("never"))
        with self.assertRaises(TypeError):
            Thread.made[0].target()
        self.assertEqual(self.jmri.replies, [])
        self.assertEqual(Queue.made[0].items, [batch("never")])

    def test_a_failure_setting_the_reply_ends_the_thread(self):
        """Fault, not fixed here: reply.setValue sits outside the try, so a reply listener that
        throws (or a reply json cannot encode) stops every later request."""
        class Broken:
            def propertyChange(self, event):
                raise JavaException("reply listener failed")
        self.reply.addPropertyChangeListener(Broken())
        self.request.setValue(batch("e3"))
        self.request.setValue(batch("never"))
        with self.assertRaises(JavaException):
            Thread.made[0].target()
        self.assertEqual([r["id"] for r in self.jmri.replies], ["e3"])
        self.assertEqual(Queue.made[0].items, [batch("never")])

    def test_ready_still_shows_the_version_after_the_thread_has_ended(self):
        """Fault, not fixed here: STS reads READY to know the script listens; a dead thread leaves it set."""
        self.jmri.fetch_error = JavaError("OutOfMemoryError")
        self.request.setValue(batch("e4"))
        with self.assertRaises(JavaError):
            Thread.made[0].target()
        self.assertEqual(self.jmri.memories.getMemory(sync.READY).getValue(), sync.VERSION)
        self.request.setValue(batch("later"))                       # still accepted, never answered
        self.assertEqual(Queue.made[0].items, [batch("later")])

    @unittest.expectedFailure
    def test_wanted_one_failure_does_not_end_the_thread(self):
        """What the thread should do; fails today (see the four tests above)."""
        self.jmri.fetch_error = JavaError("StackOverflowError")
        self.request.setValue(batch("w1"))
        try:
            Thread.made[0].target()
        except Drained:
            pass
        self.assertEqual([r.get("ok") for r in self.jmri.replies], [False])

    @unittest.expectedFailure
    def test_wanted_a_failed_fetch_reply_carries_the_request_id(self):
        """What the reply should hold; fails today (the Java-exception reply has no "id")."""
        self.jmri.fetch_error = JavaException("no CarManager")
        self.request.setValue(batch("w2"))
        self.run_worker()
        self.assertEqual(self.jmri.replies[0].get("id"), "w2")

    # --- the script run a second time (JMRI reloads it) --------------------------------

    def test_a_second_start_swaps_the_listener_and_keeps_other_listeners(self):
        first = self.request.getPropertyChangeListeners()[0]
        other = Recorder([])
        self.request.addPropertyChangeListener(other)
        sync._start()
        listeners = self.request.getPropertyChangeListeners()
        self.assertEqual(len(listeners), 2)
        self.assertIn(other, listeners)
        self.assertNotIn(first, listeners)
        self.request.setValue(batch("r1", load="Steel"))
        self.assertEqual([q.items for q in Queue.made], [[], [batch("r1", load="Steel")]])
        self.run_worker()
        self.assertEqual([r["id"] for r in self.jmri.replies], ["r1"])   # answered once, by the new thread

    def test_a_second_start_leaves_the_first_thread_waiting_on_its_own_queue(self):
        """The first thread is not stopped: it stays blocked on a queue nothing fills (daemon, so
        it does not hold JMRI open)."""
        sync._start()
        self.assertEqual([(t.name, t.daemon, t.starts) for t in Thread.made], [("STS car sync", True, 1)] * 2)
        self.assertEqual(len(Queue.made), 2)
        self.request.setValue(batch("r2"))
        self.run_worker(Thread.made[0])
        self.assertEqual(self.jmri.replies, [])


class FakeModules(unittest.TestCase):
    """jf.fake_modules, which both start-up script tests use to stand in for Java and JMRI."""

    def test_only_the_fakes_are_taken_out_again(self):
        real_json, fake_json = sys.modules["json"], types.ModuleType("json")
        late = types.ModuleType("hart_imported_during_a_test")
        self.addCleanup(sys.modules.pop, late.__name__, None)
        self.assertNotIn("java", sys.modules)
        with jf.fake_modules({"java": types.ModuleType("java"), "json": fake_json}):
            self.assertIs(sys.modules["json"], fake_json)
            sys.modules[late.__name__] = late     # as a first `import` inside a test does
        self.assertNotIn("java", sys.modules)                 # a fake that hid nothing is removed
        self.assertIs(sys.modules["json"], real_json)         # a hidden real module is back
        self.assertIs(sys.modules[late.__name__], late)       # and a module imported meanwhile stays

    def test_the_fakes_are_taken_out_when_the_body_fails(self):
        with self.assertRaises(ValueError):
            with jf.fake_modules({"java": types.ModuleType("java")}):
                raise ValueError("test body failed")
        self.assertNotIn("java", sys.modules)


if __name__ == "__main__":
    unittest.main()
