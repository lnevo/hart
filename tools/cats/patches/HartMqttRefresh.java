package cats.layout.items;

import java.awt.event.ActionEvent;
import java.awt.event.ActionListener;
import javax.swing.Timer;

/**
 * Called at end of Screen.findBounds — re-apply retained MQTT turnout/sensor
 * state after Digicon vital logic is linked.
 *
 * MQTT turnouts/sensors are often created (and retain applied) after the first
 * refresh, so we retry for ~60s. Use Appearance → <b>Refresh Screen</b> (JMRI
 * → Digicon). Do <b>not</b> use Refresh Layout — that is Digicon → JMRI and
 * will command points to Digicon's current (often still-NORMAL) frogs.
 */
public final class HartMqttRefresh {
  private HartMqttRefresh() {}

  /** Delays (ms) after findBounds for each IOSpec.refreshScreen() pass. */
  private static final int[] RETRY_MS = {
    500, 1500, 3000, 6000, 10000, 15000, 25000, 40000, 60000
  };

  public static void afterBounds() {
    IOSpec.refreshScreen();
    for (int delay : RETRY_MS) {
      Timer t = new Timer(delay, new RetryListener());
      t.setRepeats(false);
      t.start();
    }
  }

  private static final class RetryListener implements ActionListener {
    @Override
    public void actionPerformed(ActionEvent e) {
      IOSpec.refreshScreen();
      ((Timer) e.getSource()).stop();
    }
  }
}
