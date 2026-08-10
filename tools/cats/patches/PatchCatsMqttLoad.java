import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.Map;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.JarOutputStream;
import javassist.ClassPool;
import javassist.CtClass;
import javassist.CtMethod;
import javassist.LoaderClassPath;

/**
 * Minimal stock-CATS safety net so MQTT turnout feedback cannot kill Digicon.
 *
 * Stock: premature SELECTEDREPORT → PtsVitalLogic.setSelectedTrack NPE →
 * uncaught on RREventManager → AsyncDelayLine dies → occupancy frozen forever.
 *
 * This overlay does <b>not</b> write MQTT, command turnouts, or auto-refresh
 * frogs. It only keeps the event queue alive and defers track select until
 * frogs/lock processors exist.
 */
public class PatchCatsMqttLoad {
  static final String PTS = "cats/layout/vitalLogic/PtsVitalLogic";
  static final String ROUTE = "cats/layout/items/RouteInfo";
  static final String RR = "cats/rr_events/RREventManager";
  static final String PTSEDGE = "cats/layout/items/PtsEdge";

  public static void main(String[] args) throws Exception {
    if (args.length != 2) {
      System.err.println("Usage: PatchCatsMqttLoad <stock-cats.jar> <out-cats.jar>");
      System.exit(2);
    }
    Path inJar = Paths.get(args[0]);
    Path outJar = Paths.get(args[1]);

    ClassPool pool = ClassPool.getDefault();
    pool.insertClassPath(inJar.toString());
    pool.insertClassPath(new LoaderClassPath(PatchCatsMqttLoad.class.getClassLoader()));

    // Keep the queue alive — stock uncaught handler ends AsyncDelayLine.
    CtClass rr = pool.get("cats.rr_events.RREventManager");
    CtMethod consume =
        rr.getDeclaredMethod("consume", new CtClass[] {pool.get("cats.rr_events.RREvent")});
    consume.setBody(
        "{"
            + "  try {"
            + "    $1.doIt();"
            + "  } catch (Throwable t) {"
            + "    System.err.println(\"RREventManager: deferred/failed event: \" + t);"
            + "    t.printStackTrace(System.err);"
            + "  }"
            + "}");
    byte[] rrBytes = rr.toBytecode();
    rr.detach();

    CtClass route = pool.get("cats.layout.items.RouteInfo");
    CtMethod sendFb = route.getDeclaredMethod("sendFeedback");
    sendFb.setBody(
        "{"
            + "  if (VitalLogic == null) { return; }"
            + "  VitalLogic.acceptMakeEvent(Destination);"
            + "}");
    byte[] routeBytes = route.toBytecode();
    route.detach();

    CtClass ptsEdge = pool.get("cats.layout.items.PtsEdge");
    CtMethod localOk = ptsEdge.getDeclaredMethod("isLocalControlAllowed");
    localOk.insertBefore("if (MyBlock == null) { return true; }");
    byte[] ptsEdgeBytes = ptsEdge.toBytecode();
    ptsEdge.detach();

    // Defer until Frog/lock processors exist (NPE was AdvanceLockProcessor.get
    // → null.requestLockClear at PtsVitalLogic.java:564).
    CtClass pts = pool.get("cats.layout.vitalLogic.PtsVitalLogic");
    CtMethod setSel = pts.getDeclaredMethod("setSelectedTrack");
    setSel.setBody(
        "{"
            + "  if (CurrentRoute == $1) {"
            + "    if (cats.apps.Crandic.Details.get(0)) {"
            + "      System.out.println(String.valueOf(Identity) + \" requesting currently selected track: \" + CurrentRoute);"
            + "    }"
            + "    return;"
            + "  }"
            + "  if ($1 != -1 && (Frog == null || Frog[$1] == null)) {"
            + "    return;"
            + "  }"
            + "  if (CurrentRoute != -1) {"
            + "    if (UnlockRoute[CurrentRoute]) {"
            + "      cats.layout.vitalLogic.LockRequestProcessor p ="
            + "          (cats.layout.vitalLogic.LockRequestProcessor) AdvanceLockProcessor.get("
            + "              cats.layout.vitalLogic.LogicLocks.CONFLICTINGSIGNALLOCK);"
            + "      if (p != null) { p.requestLockSet(); }"
            + "    }"
            + "    cats.layout.vitalLogic.FrogVitalLogic oldFrog = Frog[CurrentRoute];"
            + "    if (oldFrog != null) {"
            + "      oldFrog.foulRoute();"
            + "      if (oldFrog.PeerLogic != null) {"
            + "        clearAdvanceLock(cats.layout.vitalLogic.LogicLocks.ROUTELOCK);"
            + "        clearAdvanceLock(cats.layout.vitalLogic.LogicLocks.PROTECTIONLOCK);"
            + "        oldFrog.PeerLogic.setAdvanceLock(cats.layout.vitalLogic.LogicLocks.CONFLICTINGSIGNALLOCK);"
            + "        FedCircuit.setApproachTrackCircuit(null);"
            + "      }"
            + "    }"
            + "  }"
            + "  CurrentRoute = $1;"
            + "  if (CurrentRoute != -1) {"
            + "    if (UnlockRoute[CurrentRoute]) {"
            + "      cats.layout.vitalLogic.LockRequestProcessor p ="
            + "          (cats.layout.vitalLogic.LockRequestProcessor) AdvanceLockProcessor.get("
            + "              cats.layout.vitalLogic.LogicLocks.CONFLICTINGSIGNALLOCK);"
            + "      if (p != null) { p.requestLockClear(); }"
            + "    }"
            + "    cats.layout.vitalLogic.FrogVitalLogic newFrog = Frog[CurrentRoute];"
            + "    if (newFrog != null) {"
            + "      FedCircuit.setApproachTrackCircuit(newFrog.lineRoute(ApproachCircuit));"
            + "      newFrog.mergeOpposingSpeed(MergedSpeed);"
            + "      if (!AdvanceLocks.contains(cats.layout.vitalLogic.LogicLocks.CONFLICTINGSIGNALLOCK)"
            + "          && newFrog.PeerLogic != null) {"
            + "        newFrog.PeerLogic.clearAdvanceLock(cats.layout.vitalLogic.LogicLocks.CONFLICTINGSIGNALLOCK);"
            + "      }"
            + "    }"
            + "  }"
            + "}");
    byte[] ptsBytes = pts.toBytecode();
    pts.detach();

    Map<String, byte[]> replace = new HashMap<>();
    replace.put(RR + ".class", rrBytes);
    replace.put(ROUTE + ".class", routeBytes);
    replace.put(PTSEDGE + ".class", ptsEdgeBytes);
    replace.put(PTS + ".class", ptsBytes);

    Files.createDirectories(outJar.getParent() != null ? outJar.getParent() : Paths.get("."));
    try (JarFile jf = new JarFile(inJar.toFile());
        JarOutputStream jos = new JarOutputStream(new FileOutputStream(outJar.toFile()))) {
      jf.stream()
          .forEach(
              entry -> {
                try {
                  jos.putNextEntry(new JarEntry(entry.getName()));
                  if (replace.containsKey(entry.getName())) {
                    jos.write(replace.get(entry.getName()));
                  } else if (!entry.isDirectory()) {
                    try (InputStream is = jf.getInputStream(entry)) {
                      is.transferTo(jos);
                    }
                  }
                  jos.closeEntry();
                } catch (IOException ex) {
                  throw new UncheckedIOException(ex);
                }
              });
    }
    System.out.println("Wrote " + outJar);
    System.out.println("  minimal: RREventManager.consume try/catch");
    System.out.println("  minimal: RouteInfo.sendFeedback VitalLogic null-guard");
    System.out.println("  minimal: PtsEdge.isLocalControlAllowed MyBlock null-guard");
    System.out.println("  minimal: PtsVitalLogic.setSelectedTrack defer + lock null-guard");
  }
}
