import java.io.FileOutputStream;
import java.nio.file.Path;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;
import javassist.ClassPool;
import javassist.CtClass;
import javassist.CtMethod;
import javassist.CtNewMethod;
import javassist.LoaderClassPath;

/**
 * Startup overlays:
 * <ul>
 *   <li>JMRI MqttAdapter — table load vs retained MQTT used to CME the Paho
 *       callback, drop the connection, then ERROR on every subscribe.
 *       Also skip publish to {@code _discard/**} (retired sensor send sink).
 *   <li>CATS BlkEdge/Track — a second Block on an edge/track is ignored by
 *       stock CATS after a WARN (occupancy cuts + plant frogs). Skip the warn.
 *   <li>CATS OperationsClient — loopback ops-server probe is unused here.
 * </ul>
 */
public class PatchMqttCme {
  public static void main(String[] args) throws Exception {
    if (args.length != 3) {
      System.err.println("Usage: PatchMqttCme <jmri.jar> <cats.jar> <out-overlay.jar>");
      System.exit(2);
    }
    Path jmriJar = Path.of(args[0]);
    Path catsJar = Path.of(args[1]);
    Path outJar = Path.of(args[2]);

    ClassPool pool = ClassPool.getDefault();
    pool.insertClassPath(jmriJar.toString());
    pool.insertClassPath(catsJar.toString());
    Path paho = jmriJar.getParent().resolve("lib/org.eclipse.paho.client.mqttv3-1.2.5.jar");
    if (paho.toFile().isFile()) {
      pool.insertClassPath(paho.toString());
    }
    pool.insertClassPath(new LoaderClassPath(PatchMqttCme.class.getClassLoader()));

    CtClass mqtt = patchMqtt(pool);
    CtClass blk = patchBlkEdge(pool);
    CtClass track = patchTrack(pool);
    CtClass ops = patchOperationsClient(pool);

    try (JarOutputStream jos = new JarOutputStream(new FileOutputStream(outJar.toFile()))) {
      put(jos, "jmri/jmrix/mqtt/MqttAdapter.class", mqtt.toBytecode());
      put(jos, "cats/layout/items/BlkEdge.class", blk.toBytecode());
      put(jos, "cats/layout/items/Track.class", track.toBytecode());
      put(jos, "cats/network/OperationsClient.class", ops.toBytecode());
    }
    mqtt.detach();
    blk.detach();
    track.detach();
    ops.detach();
    System.out.println("wrote " + outJar);
  }

  private static void put(JarOutputStream jos, String name, byte[] bytes) throws Exception {
    jos.putNextEntry(new JarEntry(name));
    jos.write(bytes);
    jos.closeEntry();
  }

  private static CtClass patchMqtt(ClassPool pool) throws Exception {
    CtClass cc = pool.get("jmri.jmrix.mqtt.MqttAdapter");
    CtMethod orig = cc.getDeclaredMethod("messageArrived");
    orig.setName("messageArrivedImpl");
    cc.addMethod(
        CtNewMethod.make(
            "public void messageArrived(java.lang.String topic,"
                + " org.eclipse.paho.client.mqttv3.MqttMessage message)"
                + " throws java.lang.Exception {"
                + "  try {"
                + "    if (mqttEventListeners == null) { messageArrivedImpl(topic, message); return; }"
                + "    synchronized (mqttEventListeners) { messageArrivedImpl(topic, message); }"
                + "  } catch (java.util.ConcurrentModificationException e) {"
                + "    System.err.println(\"MQTT messageArrived CME ignored: \" + e);"
                + "  }"
                + "}",
            cc));
    wrapSync(cc, "subscribe");
    wrapSync(cc, "unsubscribe");
    // 11.3 was a trash-can so MqttSensor.setKnownState would not hit LCOS.
    // It still retained INACTIVE on _discard/cmd/sensor/{addr}. Drop those.
    CtMethod[] pubs = cc.getDeclaredMethods("publish");
    for (int i = 0; i < pubs.length; i++) {
      if (pubs[i].getParameterTypes().length == 3) {
        pubs[i].insertBefore("if ($1 != null && $1.startsWith(\"_discard\")) { return; }");
      }
    }
    return cc;
  }

  private static void wrapSync(CtClass cc, String name) throws Exception {
    CtMethod orig = cc.getDeclaredMethod(name);
    String impl = name + "Impl";
    orig.setName(impl);
    CtClass[] params = orig.getParameterTypes();
    StringBuilder sig = new StringBuilder("public void " + name + "(");
    for (int i = 0; i < params.length; i++) {
      if (i > 0) {
        sig.append(", ");
      }
      sig.append(params[i].getName()).append(" a").append(i);
    }
    sig.append(") { try {");
    sig.append("  if (mqttEventListeners == null) { ").append(impl).append("(");
    for (int i = 0; i < params.length; i++) {
      if (i > 0) {
        sig.append(", ");
      }
      sig.append("a").append(i);
    }
    sig.append("); return; }");
    sig.append("  synchronized (mqttEventListeners) { ").append(impl).append("(");
    for (int i = 0; i < params.length; i++) {
      if (i > 0) {
        sig.append(", ");
      }
      sig.append("a").append(i);
    }
    sig.append(
        "); } } catch (java.util.ConcurrentModificationException e) {"
            + " System.err.println(\"MQTT "
            + name
            + " CME ignored: \" + e); } }");
    cc.addMethod(CtNewMethod.make(sig.toString(), cc));
  }

  private static CtClass patchBlkEdge(ClassPool pool) throws Exception {
    CtClass cc = pool.get("cats.layout.items.BlkEdge");
    CtMethod m =
        cc.getDeclaredMethod(
            "setBlock", new CtClass[] {pool.get("cats.layout.items.Block")});
    // Stock keeps the first Block and only warns on a second instance (same or
    // different name). Occupancy cuts always hit this path.
    m.insertBefore(
        "if ($1 == cats.layout.items.Block.BlockHolder) { return; }"
            + "if (MyBlock != null && MyBlock != cats.layout.items.Block.BlockHolder"
            + "    && $1 != MyBlock) { return; }");
    return cc;
  }

  private static CtClass patchTrack(ClassPool pool) throws Exception {
    CtClass cc = pool.get("cats.layout.items.Track");
    CtMethod m =
        cc.getDeclaredMethod(
            "setBlock", new CtClass[] {pool.get("cats.layout.items.Block")});
    m.insertBefore("if (TrackBlock != null) { return; }");
    return cc;
  }

  private static CtClass patchOperationsClient(ClassPool pool) throws Exception {
    CtClass cc = pool.get("cats.network.OperationsClient");
    CtMethod inet =
        cc.getDeclaredMethod(
            "establishConnection",
            new CtClass[] {pool.get("java.net.InetAddress"), CtClass.intType});
    inet.insertBefore("if ($1 != null && $1.isLoopbackAddress()) { return; }");
    CtMethod host =
        cc.getDeclaredMethod(
            "establishConnection",
            new CtClass[] {pool.get("java.lang.String"), CtClass.intType});
    host.insertBefore(
        "if ($1 != null && (\"127.0.0.1\".equals($1) || \"localhost\".equalsIgnoreCase($1))) {"
            + " return; }");
    return cc;
  }
}
