package info.openrocket.core.simulation;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Arrays;
import java.util.Locale;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import info.openrocket.core.document.OpenRocketDocument;
import info.openrocket.core.document.Simulation;
import info.openrocket.core.file.GeneralRocketLoader;
import info.openrocket.core.logging.SimulationAbort;
import info.openrocket.core.simulation.listeners.AbstractSimulationListener;
import info.openrocket.core.util.BaseTestCase;
import info.openrocket.core.util.Coordinate;

/**
 * Throwaway probe: runs the first simulation of every .ork in TE_ORK_DIR at several steady winds, with all
 * randomness pinned, and records per branch the TUMBLE time, apogee, landing time and any abort.
 * Env: TE_ORK_DIR, TE_OUT (file), TE_WINDS (m/s, csv).
 */
public class TumbleEventProbeTest extends BaseTestCase {

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
	public void run() throws Exception {
		File[] orks = new File(System.getenv("TE_ORK_DIR")).listFiles((d, n) -> n.endsWith(".ork"));
		Arrays.sort(orks);
		String[] winds = System.getenv().getOrDefault("TE_WINDS", "0,5,10").split(",");
		try (PrintWriter pw = new PrintWriter(new FileWriter(System.getenv("TE_OUT")))) {
			pw.println("rocket\twind\tbranch\ttumble_t\tapogee_m\tland_t\tabort\tmax_aoa_deg");
			for (File ork : orks) {
				for (String ws : winds) {
					OpenRocketDocument doc = new GeneralRocketLoader(ork).load();
					Simulation sim = doc.getSimulations().get(0);
					SimulationOptions o = sim.getOptions();
					o.setRandomSeed(0);
					o.setRandomSeedFixed(true);
					o.getWindModel().setSeed(0);
					o.setWindTurbulenceIntensity(0);
					o.setWindSpeedAverage(0);
					o.setISAAtmosphere(true);
					String name = ork.getName().replace(".ork", "").replace(' ', '_');
					if ("1".equals(System.getenv("TE_NO_RECOVERY"))) {
						// Recovery disabled: forces every flight through an unassisted apogee turnover.
						for (info.openrocket.core.rocketcomponent.RocketComponent c : doc.getRocket()) {
							if (c instanceof info.openrocket.core.rocketcomponent.RecoveryDevice rd) {
								rd.getDeploymentConfigurations().getDefault().setDeployEvent(
										info.openrocket.core.rocketcomponent.DeploymentConfiguration.DeployEvent.NEVER);
								rd.getDeploymentConfigurations().get(sim.getFlightConfigurationId()).setDeployEvent(
										info.openrocket.core.rocketcomponent.DeploymentConfiguration.DeployEvent.NEVER);
							}
						}
					}
					try {
						sim.simulate(new SteadyWind(Double.parseDouble(ws)));
					} catch (Exception e) {
						pw.println(name + "\t" + ws + "\t-\tNaN\tNaN\tNaN\tEXCEPTION:" + e.getClass().getSimpleName() + "\tNaN");
						continue;
					}
					FlightData fd = sim.getSimulatedData();
					String dump = System.getenv("TE_DUMP_DIR");
					if (dump != null) {
						FlightDataBranch b0 = fd.getBranch(0);
						FlightDataType[] cols = { FlightDataType.TYPE_TIME, FlightDataType.TYPE_ALTITUDE,
								FlightDataType.TYPE_VELOCITY_Z, FlightDataType.TYPE_AOA,
								FlightDataType.TYPE_ORIENTATION_THETA, FlightDataType.TYPE_CP_LOCATION,
								FlightDataType.TYPE_CG_LOCATION, FlightDataType.TYPE_STABILITY,
								FlightDataType.TYPE_NATURAL_FREQUENCY, FlightDataType.TYPE_MACH_NUMBER,
								FlightDataType.TYPE_PITCH_MOMENT_COEFF, FlightDataType.TYPE_NORMAL_FORCE_COEFF,
								FlightDataType.TYPE_PITCH_RATE };
						try (PrintWriter dw = new PrintWriter(new FileWriter(new File(dump, name + "_w" + ws + ".tsv")))) {
							StringBuilder h = new StringBuilder();
							for (FlightDataType c : cols) {
								h.append(c.getName().replace(' ', '_')).append('\t');
							}
							dw.println(h.toString().trim());
							java.util.List<Double> tt = b0.get(FlightDataType.TYPE_TIME);
							for (int k = 0; k < tt.size(); k++) {
								StringBuilder r = new StringBuilder();
								for (FlightDataType c : cols) {
									java.util.List<Double> col = b0.get(c);
									r.append(String.format(Locale.ROOT, "%.6g",
											col == null || k >= col.size() ? Double.NaN : col.get(k))).append('\t');
								}
								dw.println(r.toString().trim());
							}
							for (FlightEvent ev : b0.getEvents()) {
								dw.println("# " + ev.getType() + " " + ev.getTime());
							}
						}
					}
					for (int i = 0; i < fd.getBranchCount(); i++) {
						FlightDataBranch b = fd.getBranch(i);
						FlightEvent tumble = b.getFirstEvent(FlightEvent.Type.TUMBLE);
						FlightEvent abort = b.getFirstEvent(FlightEvent.Type.SIM_ABORT);
						FlightEvent land = b.getFirstEvent(FlightEvent.Type.GROUND_HIT);
						double maxAoa = Double.NaN;
						java.util.List<Double> aoa = b.get(FlightDataType.TYPE_AOA);
						java.util.List<Double> alt = b.get(FlightDataType.TYPE_ALTITUDE);
						if (aoa != null) {
							for (int k = 0; k < aoa.size(); k++) {
								// skip the pad, where airspeed is wind only
								if (alt.get(k) > 5 && !Double.isNaN(aoa.get(k))
										&& (Double.isNaN(maxAoa) || aoa.get(k) > maxAoa)) {
									maxAoa = aoa.get(k);
								}
							}
						}
						pw.println(String.format(Locale.ROOT, "%s\t%s\t%d\t%.4f\t%.3f\t%.4f\t%s\t%.2f", name, ws, i,
								tumble == null ? Double.NaN : tumble.getTime(),
								b.getMaximum(FlightDataType.TYPE_ALTITUDE),
								land == null ? Double.NaN : land.getTime(),
								abort == null ? "-" : ((SimulationAbort) abort.getData()).getCause().toString(),
								Double.isNaN(maxAoa) ? Double.NaN : Math.toDegrees(maxAoa)));
					}
				}
			}
		}
	}
}
