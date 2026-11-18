package info.openrocket.core.simulation;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import info.openrocket.core.document.OpenRocketDocument;
import info.openrocket.core.document.Simulation;
import info.openrocket.core.file.GeneralRocketLoader;
import info.openrocket.core.logging.SimulationAbort;
import info.openrocket.core.rocketcomponent.DeploymentConfiguration;
import info.openrocket.core.rocketcomponent.RecoveryDevice;
import info.openrocket.core.rocketcomponent.RocketComponent;
import info.openrocket.core.simulation.listeners.AbstractSimulationListener;
import info.openrocket.core.util.BaseTestCase;
import info.openrocket.core.util.Coordinate;

/**
 * Throwaway probe: every simulation of every .ork in SW_ORK_DIR, at each steady wind in SW_WINDS (m/s), with
 * recovery as designed and disabled, randomness pinned. One row per flight branch.
 * Env: SW_ORK_DIR, SW_OUT, SW_WINDS, SW_DUMP_DIR + SW_DUMP_KEYS ("rocket|sim|wind|rec;..." to dump branch-0
 * time series of selected runs).
 */
public class TumbleSweepProbeTest extends BaseTestCase {

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

	@BeforeAll
	public static void loadDatabases() throws Exception {
		info.openrocket.core.file.openrocket.ExampleFilesTest.setUp();
	}

	@Test
	public void sweep() throws Exception {
		File[] orks = new File(System.getenv("SW_ORK_DIR")).listFiles((d, n) -> n.endsWith(".ork"));
		Arrays.sort(orks);
		String[] winds = System.getenv().getOrDefault("SW_WINDS", "0").split(",");
		Set<String> dumpKeys = new HashSet<>();
		String dumpDir = System.getenv("SW_DUMP_DIR");
		if (System.getenv("SW_DUMP_KEYS") != null) {
			dumpKeys.addAll(Arrays.asList(System.getenv("SW_DUMP_KEYS").split(";")));
		}
		boolean onlyDump = dumpDir != null && !dumpKeys.isEmpty();
		try (PrintWriter pw = new PrintWriter(new FileWriter(System.getenv("SW_OUT")))) {
			pw.println("rocket\tsim\twind\trec\tbranch\ttumble_t\tburnout_t\tapogee_m\tland_t\tabort\tt_aoa_20_90\tn_points");
			for (File ork : orks) {
				String name = ork.getName().replace(".ork", "").replace(' ', '_');
				int nSims = new GeneralRocketLoader(ork).load().getSimulations().size();
				for (int s = 0; s < nSims; s++) {
					for (String ws : winds) {
						for (int rec = 1; rec >= 0; rec--) {
							String key = name + "|" + s + "|" + ws + "|" + rec;
							if (onlyDump && !dumpKeys.contains(key)) {
								continue;
							}
							OpenRocketDocument doc = new GeneralRocketLoader(ork).load();
							Simulation sim = doc.getSimulations().get(s);
							SimulationOptions o = sim.getOptions();
							o.setRandomSeed(0);
							o.setRandomSeedFixed(true);
							o.getWindModel().setSeed(0);
							o.setWindTurbulenceIntensity(0);
							o.setWindSpeedAverage(0);
							o.setISAAtmosphere(true);
							if (System.getenv("SW_DT_EPS") != null) {
								// numerical-sensitivity control: perturb the time step by a negligible relative amount
								o.setTimeStep(o.getTimeStep() * (1 + Double.parseDouble(System.getenv("SW_DT_EPS"))));
							}
							if (rec == 0) {
								for (RocketComponent c : doc.getRocket()) {
									if (c instanceof RecoveryDevice rd) {
										rd.getDeploymentConfigurations().getDefault()
												.setDeployEvent(DeploymentConfiguration.DeployEvent.NEVER);
										rd.getDeploymentConfigurations().get(sim.getFlightConfigurationId())
												.setDeployEvent(DeploymentConfiguration.DeployEvent.NEVER);
									}
								}
							}
							try {
								sim.simulate(new SteadyWind(Double.parseDouble(ws)));
							} catch (Exception e) {
								pw.println(name + "\t" + s + "\t" + ws + "\t" + rec + "\t-\tNaN\tNaN\tNaN\tNaN\tEXCEPTION:"
										+ e.getClass().getSimpleName() + "\tNaN\t0");
								continue;
							}
							FlightData fd = sim.getSimulatedData();
							if (onlyDump) {
								dump(new File(dumpDir, key.replace('|', '_') + ".tsv"), fd.getBranch(0));
							}
							for (int i = 0; i < fd.getBranchCount(); i++) {
								FlightDataBranch b = fd.getBranch(i);
								pw.println(String.format(Locale.ROOT, "%s\t%d\t%s\t%d\t%d\t%.6f\t%.6f\t%.6f\t%.6f\t%s\t%.6f\t%d",
										name, s, ws, rec, i,
										time(b, FlightEvent.Type.TUMBLE), time(b, FlightEvent.Type.BURNOUT),
										b.getMaximum(FlightDataType.TYPE_ALTITUDE), time(b, FlightEvent.Type.GROUND_HIT),
										abortCause(b), timeAoaBand(b), b.getLength()));
							}
						}
					}
				}
			}
		}
	}

	private static double time(FlightDataBranch b, FlightEvent.Type type) {
		FlightEvent e = b.getFirstEvent(type);
		return e == null ? Double.NaN : e.getTime();
	}

	private static String abortCause(FlightDataBranch b) {
		FlightEvent e = b.getFirstEvent(FlightEvent.Type.SIM_ABORT);
		return e == null ? "-" : ((SimulationAbort) e.getData()).getCause().name();
	}

	/**
	 * Time spent with 20 deg < AoA < 90 deg, off the pad (altitude above 5 m), before the first TUMBLE or
	 * recovery deployment: the regime in which the reported CP differs from the force-consistent one.
	 */
	private static double timeAoaBand(FlightDataBranch b) {
		List<Double> t = b.get(FlightDataType.TYPE_TIME);
		List<Double> aoa = b.get(FlightDataType.TYPE_AOA);
		List<Double> alt = b.get(FlightDataType.TYPE_ALTITUDE);
		if (t == null || aoa == null || alt == null) {
			return Double.NaN;
		}
		double end = Double.POSITIVE_INFINITY;
		for (FlightEvent e : b.getEvents()) {
			if (e.getType() == FlightEvent.Type.TUMBLE || e.getType() == FlightEvent.Type.RECOVERY_DEVICE_DEPLOYMENT) {
				end = Math.min(end, e.getTime());
			}
		}
		double sum = 0;
		for (int k = 1; k < t.size(); k++) {
			if (t.get(k) > end) {
				break;
			}
			double a = Math.toDegrees(aoa.get(k));
			if (alt.get(k) > 5 && a > 20 && a < 90) {
				sum += t.get(k) - t.get(k - 1);
			}
		}
		return sum;
	}

	private static void dump(File f, FlightDataBranch b) throws Exception {
		FlightDataType[] cols = { FlightDataType.TYPE_TIME, FlightDataType.TYPE_ALTITUDE, FlightDataType.TYPE_VELOCITY_Z,
				FlightDataType.TYPE_AOA, FlightDataType.TYPE_ORIENTATION_THETA, FlightDataType.TYPE_CP_LOCATION,
				FlightDataType.TYPE_CG_LOCATION, FlightDataType.TYPE_STABILITY, FlightDataType.TYPE_NATURAL_FREQUENCY,
				FlightDataType.TYPE_THRUST_FORCE, FlightDataType.TYPE_PITCH_RATE, FlightDataType.TYPE_POSITION_X,
				FlightDataType.TYPE_VELOCITY_XY, FlightDataType.TYPE_NORMAL_FORCE_COEFF,
				FlightDataType.TYPE_PITCH_MOMENT_COEFF, FlightDataType.TYPE_PITCH_DAMPING_MOMENT_COEFF,
				FlightDataType.TYPE_TIME_STEP, FlightDataType.TYPE_YAW_RATE, FlightDataType.TYPE_ROLL_RATE };
		try (PrintWriter dw = new PrintWriter(new FileWriter(f))) {
			StringBuilder h = new StringBuilder();
			for (FlightDataType c : cols) {
				h.append(c.getName().replace(' ', '_')).append('\t');
			}
			dw.println(h.toString().trim());
			List<Double> tt = b.get(FlightDataType.TYPE_TIME);
			for (int k = 0; k < tt.size(); k++) {
				StringBuilder r = new StringBuilder();
				for (FlightDataType c : cols) {
					List<Double> col = b.get(c);
					r.append(String.format(Locale.ROOT, "%.17g", col == null || k >= col.size() ? Double.NaN : col.get(k)))
							.append('\t');
				}
				dw.println(r.toString().trim());
			}
			for (FlightEvent ev : b.getEvents()) {
				dw.println("# " + ev.getType().name() + " " + ev.getTime());
			}
		}
	}
}
