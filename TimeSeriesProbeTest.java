package info.openrocket.core.simulation;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.List;
import java.util.Locale;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import info.openrocket.core.document.Simulation;
import info.openrocket.core.file.GeneralRocketLoader;
import info.openrocket.core.util.BaseTestCase;
import info.openrocket.core.util.GeodeticComputationStrategy;

/**
 * Throwaway probe for issue #2489: per-step time series of the TRF rocket up to apogee.
 * Wind is a steady listener-supplied vector along +X (air moving toward -X, so +X is upwind).
 * Env: TS_ORK (file), TS_WINDS_MPH (csv), TS_LABEL, TS_OUT (dir), TS_FLAT=1 (flat-earth geodetics).
 */
public class TimeSeriesProbeTest extends BaseTestCase {

	@BeforeAll
	public static void loadDatabases() throws Exception {
		info.openrocket.core.file.openrocket.ExampleFilesTest.setUp();
	}

	private static final FlightDataType[] COLS = {
			FlightDataType.TYPE_TIME, FlightDataType.TYPE_ALTITUDE, FlightDataType.TYPE_POSITION_X,
			FlightDataType.TYPE_VELOCITY_XY, FlightDataType.TYPE_VELOCITY_Z, FlightDataType.TYPE_AOA,
			FlightDataType.TYPE_ORIENTATION_THETA, FlightDataType.TYPE_ORIENTATION_PHI,
			FlightDataType.TYPE_NORMAL_FORCE_COEFF, FlightDataType.TYPE_PITCH_MOMENT_COEFF,
			FlightDataType.TYPE_PITCH_DAMPING_MOMENT_COEFF, FlightDataType.TYPE_CP_LOCATION,
			FlightDataType.TYPE_CG_LOCATION, FlightDataType.TYPE_PITCH_RATE, FlightDataType.TYPE_MACH_NUMBER,
			FlightDataType.TYPE_THRUST_FORCE, FlightDataType.TYPE_MASS, FlightDataType.TYPE_LONGITUDINAL_INERTIA,
			FlightDataType.TYPE_AXIAL_DRAG_COEFF, FlightDataType.TYPE_DRAG_COEFF, FlightDataType.TYPE_AIR_DENSITY,
			FlightDataType.TYPE_SPEED_OF_SOUND, FlightDataType.TYPE_GRAVITY, FlightDataType.TYPE_VELOCITY_TOTAL,
			FlightDataType.TYPE_POSITION_Y };

	@Test
	public void dump() throws Exception {
		String ork = System.getenv("TS_ORK");
		String label = System.getenv().getOrDefault("TS_LABEL", "ts");
		File out = new File(System.getenv("TS_OUT"));
		out.mkdirs();
		boolean flat = "1".equals(System.getenv("TS_FLAT"));
		StringBuilder summary = new StringBuilder("label\tmph\tapogee_m\tx_apo_m\tt_apo\n");
		for (String s : System.getenv().getOrDefault("TS_WINDS_MPH", "15,30").split(",")) {
			double mph = Double.parseDouble(s);
			Simulation sim = new GeneralRocketLoader(new File(ork)).load().getSimulations().get(0);
			sim.getOptions().setISAAtmosphere(true);
			sim.getOptions().setLaunchRodAngle(0);
			sim.getOptions().setWindSpeedAverage(0);
			sim.getOptions().setWindTurbulenceIntensity(0);
			if (flat) {
				sim.getOptions().setGeodeticComputation(GeodeticComputationStrategy.FLAT);
			}
			if (System.getenv("TS_ROD") != null) {
				sim.getOptions().setLaunchRodLength(Double.parseDouble(System.getenv("TS_ROD")));
			}
			if (System.getenv("TS_DT") != null) {
				sim.getOptions().setTimeStep(Double.parseDouble(System.getenv("TS_DT")));
			}
			if (System.getenv("TS_STEPPER") != null) {
				sim.getOptions().setSimulationStepperMethodChoice(
						info.openrocket.core.simulation.SimulationStepperMethod.valueOf(System.getenv("TS_STEPPER")));
			}
			sim.simulate(new WeathercockProbeTest.SteadyWind(mph * 0.44704));
			FlightDataBranch b = sim.getSimulatedData().getBranch(0);
			FlightEvent apo = b.getFirstEvent(FlightEvent.Type.APOGEE);
			List<Double> t = b.get(FlightDataType.TYPE_TIME);
			try (PrintWriter pw = new PrintWriter(new FileWriter(new File(out, label + "_" + (int) mph + "mph.tsv")))) {
				StringBuilder h = new StringBuilder();
				for (FlightDataType c : COLS) {
					h.append(c.getName().replace(' ', '_')).append('\t');
				}
				pw.println(h.toString().trim());
				for (int i = 0; i < t.size() && t.get(i) <= apo.getTime() + 1e-9; i++) {
					StringBuilder r = new StringBuilder();
					for (FlightDataType c : COLS) {
						List<Double> col = b.get(c);
						double v = col == null || i >= col.size() ? Double.NaN : col.get(i);
						r.append(String.format(Locale.ROOT, "%.6g", v)).append('\t');
					}
					pw.println(r.toString().trim());
				}
			}
			int iApo = 0;
			for (int i = 0; i < t.size(); i++) {
				if (t.get(i) <= apo.getTime() + 1e-9) {
					iApo = i;
				}
			}
			summary.append(String.format(Locale.ROOT, "%s\t%.0f\t%.3f\t%.3f\t%.3f\n", label, mph,
					b.get(FlightDataType.TYPE_ALTITUDE).get(iApo), b.get(FlightDataType.TYPE_POSITION_X).get(iApo),
					apo.getTime()));
		}
		try (PrintWriter pw = new PrintWriter(new FileWriter(new File(out, label + "_summary.tsv")))) {
			pw.print(summary);
		}
		System.out.print(summary);
	}
}
