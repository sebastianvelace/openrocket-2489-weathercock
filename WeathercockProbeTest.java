package info.openrocket.core.simulation;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import info.openrocket.core.document.OpenRocketDocument;
import info.openrocket.core.document.Simulation;
import info.openrocket.core.file.GeneralRocketLoader;
import info.openrocket.core.simulation.listeners.AbstractSimulationListener;
import info.openrocket.core.util.BaseTestCase;
import info.openrocket.core.util.Coordinate;
import info.openrocket.core.util.TestRockets;

/**
 * Throwaway measurement probe for issue #2489 (weathercocking). Not for upstream.
 * Steady crosswind along +X supplied by a listener (no turbulence, nothing random),
 * vertical launch. With OpenRocket's convention (airspeed = velocity + wind) +X is upwind.
 * Env: WC_LABEL, WC_ORK_DIR (directory of .ork files; also skips the built-in Estes run),
 * WC_WINDS_MPH (csv), WC_OUT_DIR.
 */
public class WeathercockProbeTest extends BaseTestCase {

	private static final String ORK_DIR = "work/orks";
	private static final String OUT_DIR = "work/out";
	private static final double[] WINDS = { 0, 2, 4, 6, 8 };

	public static class SteadyWind extends AbstractSimulationListener {
		private final double speed;

		public SteadyWind(double speed) {
			this.speed = speed;
		}

		@Override
		public Coordinate preWindModel(SimulationStatus status) {
			return new Coordinate(speed, 0, 0);
		}

		@Override
		public boolean isSystemListener() {
			return true;
		}
	}

	@org.junit.jupiter.api.BeforeAll
	public static void loadDatabases() throws Exception {
		// Binds the component preset and motor databases needed to load .ork files.
		info.openrocket.core.file.openrocket.ExampleFilesTest.setUp();
	}

	@Test
	public void probe() throws Exception {
		String label = System.getenv().getOrDefault("WC_LABEL", "unknown");
		List<String> rows = new ArrayList<>();
		rows.add("label\trocket\twind\tapogee_m\tx_apo_m\ty_apo_m\tapo_angle_deg\ttilt_bo_deg\tmax_tilt_deg\tx_bo_m\tv_rod_ms\tx_land_m\tt_bo\tt_apo\taborted");

		String orkDir = System.getenv().getOrDefault("WC_ORK_DIR", ORK_DIR);
		double[] winds = WINDS;
		if (System.getenv("WC_WINDS_MPH") != null) {
			String[] parts = System.getenv("WC_WINDS_MPH").split(",");
			winds = new double[parts.length];
			for (int i = 0; i < parts.length; i++) {
				winds[i] = Double.parseDouble(parts[i]) * 0.44704;
			}
		}
		boolean skipEstes = System.getenv("WC_ORK_DIR") != null;

		// Programmatic rocket: independent of file loading.
		for (double w : skipEstes ? new double[0] : WINDS) {
			Simulation sim = new Simulation(TestRockets.makeEstesAlphaIII());
			sim.setFlightConfigurationId(TestRockets.TEST_FCID_0);
			// Test preferences default every option to 0; set the ones that matter.
			sim.getOptions().setTimeStep(0.01);
			sim.getOptions().setLaunchRodLength(1.0);
			configure(sim);
			rows.add(run(label, "EstesAlphaIII", sim, w));
		}

		File[] orks = new File(orkDir).listFiles((d, n) -> n.endsWith(".ork"));
		java.util.Arrays.sort(orks);
		for (File ork : orks) {
			for (double w : winds) {
				OpenRocketDocument doc = new GeneralRocketLoader(ork).load();
				Simulation sim = doc.getSimulations().get(0);
				configure(sim);
				rows.add(run(label, ork.getName().replace(".ork", "").replace(' ', '_'), sim, w));
			}
		}

		new File(OUT_DIR).mkdirs();
		String outDir = System.getenv().getOrDefault("WC_OUT_DIR", OUT_DIR);
		new File(outDir).mkdirs();
		try (PrintWriter pw = new PrintWriter(new FileWriter(new File(outDir, label + ".tsv")))) {
			for (String r : rows) {
				pw.println(r);
				System.out.println("WC " + r);
			}
		}
	}

	private static void configure(Simulation sim) {
		sim.getOptions().setISAAtmosphere(true);
		sim.getOptions().setLaunchRodAngle(0);
		sim.getOptions().setWindSpeedAverage(0);
		sim.getOptions().setWindTurbulenceIntensity(0);
	}

	private static void progress(String msg) {
		try (PrintWriter pw = new PrintWriter(new FileWriter(new File(OUT_DIR, "progress.log"), true))) {
			pw.println(java.time.LocalTime.now() + " " + msg);
		} catch (Exception ignored) {
		}
	}

	private static String run(String label, String name, Simulation sim, double wind) throws Exception {
		new File(OUT_DIR).mkdirs();
		progress("START " + label + " " + name + " w=" + wind + " stepper=" + sim.getOptions().getSimulationStepperMethodChoice()
				+ " dt=" + sim.getOptions().getTimeStep() + " rod=" + sim.getOptions().getLaunchRodLength());
		if (!(sim.getOptions().getTimeStep() > 0)) {
			throw new IllegalStateException("time step must be positive for " + name);
		}
		long t0 = System.nanoTime();
		sim.simulate(new SteadyWind(wind));
		FlightDataBranch b0 = sim.getSimulatedData().getBranch(0);
		progress("END   " + name + " w=" + wind + " " + (System.nanoTime() - t0) / 1e9 + " s, points="
				+ b0.getLength() + ", branches=" + sim.getSimulatedData().getBranchCount());
		FlightDataBranch b = sim.getSimulatedData().getBranch(0);
		List<Double> t = b.get(FlightDataType.TYPE_TIME);
		List<Double> h = b.get(FlightDataType.TYPE_ALTITUDE);
		List<Double> x = b.get(FlightDataType.TYPE_POSITION_X);
		List<Double> y = b.get(FlightDataType.TYPE_POSITION_Y);
		List<Double> th = b.get(FlightDataType.TYPE_ORIENTATION_THETA);

		FlightEvent bo = b.getFirstEvent(FlightEvent.Type.BURNOUT);
		FlightEvent apo = b.getFirstEvent(FlightEvent.Type.APOGEE);
		boolean aborted = b.getFirstEvent(FlightEvent.Type.SIM_ABORT) != null;
		double tBo = bo == null ? Double.NaN : bo.getTime();
		double tApo = apo == null ? Double.NaN : apo.getTime();

		List<Double> ph = b.get(FlightDataType.TYPE_ORIENTATION_PHI);
		List<Double> vt = b.get(FlightDataType.TYPE_VELOCITY_TOTAL);
		FlightEvent rod = b.getFirstEvent(FlightEvent.Type.LAUNCHROD);
		double tRod = rod == null ? Double.NaN : rod.getTime();

		int iApo = index(t, tApo);
		int iBo = index(t, tBo);
		int iRod = index(t, tRod);
		// Signed tilt of the rocket axis in the X-Z plane, degrees from vertical,
		// positive toward +X (upwind with OpenRocket's wind sign convention).
		double maxTilt = 0;
		for (int i = 0; i <= iApo && i < th.size(); i++) {
			double tilt = tiltX(th.get(i), ph.get(i));
			if (Math.abs(tilt) > Math.abs(maxTilt)) {
				maxTilt = tilt;
			}
		}
		int iEnd = t.size() - 1;
		double hA = h.get(iApo), xA = x.get(iApo), yA = y.get(iApo);
		double drift = Math.toDegrees(Math.atan2(xA, hA));
		return String.format(java.util.Locale.ROOT,
				"%s\t%s\t%.3f\t%.3f\t%.3f\t%.3f\t%.3f\t%.3f\t%.3f\t%.3f\t%.3f\t%.3f\t%.3f\t%.3f\t%b",
				label, name, wind, hA, xA, yA, drift,
				tiltX(th.get(iBo), ph.get(iBo)), maxTilt, x.get(iBo), vt.get(iRod), x.get(iEnd), tBo, tApo, aborted);
	}

	private static double tiltX(double theta, double phi) {
		double cx = Math.cos(theta) * Math.sin(phi);
		double cz = Math.sin(theta);
		return Math.toDegrees(Math.atan2(cx, cz));
	}

	/** Last data index with time <= target (the full branch if target is NaN). */
	private static int index(List<Double> t, double target) {
		if (Double.isNaN(target)) {
			return t.size() - 1;
		}
		int idx = 0;
		for (int i = 0; i < t.size(); i++) {
			if (t.get(i) <= target + 1e-9) {
				idx = i;
			}
		}
		return idx;
	}
}
