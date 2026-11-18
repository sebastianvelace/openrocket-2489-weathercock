package info.openrocket.core.simulation;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Arrays;
import java.util.Locale;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import info.openrocket.core.aerodynamics.AerodynamicForces;
import info.openrocket.core.aerodynamics.BarrowmanCalculator;
import info.openrocket.core.aerodynamics.FlightConditions;
import info.openrocket.core.document.OpenRocketDocument;
import info.openrocket.core.document.Simulation;
import info.openrocket.core.file.GeneralRocketLoader;
import info.openrocket.core.logging.WarningSet;
import info.openrocket.core.masscalc.MassCalculator;
import info.openrocket.core.rocketcomponent.FlightConfiguration;
import info.openrocket.core.util.BaseTestCase;

/**
 * Throwaway probe: reported CP (weighted by the CP weights) versus the CP implied by the summed normal force
 * and pitch moment (Cm * Lref / CN), from 0 to 90 degrees angle of attack, for every .ork in CP_ORK_DIR.
 * Env: CP_ORK_DIR, CP_OUT (file), CP_MACH (default 0.3).
 */
public class CpConsistencyProbeTest extends BaseTestCase {

	@BeforeAll
	public static void loadDatabases() throws Exception {
		info.openrocket.core.file.openrocket.ExampleFilesTest.setUp();
	}

	@Test
	public void sweep() throws Exception {
		double mach = Double.parseDouble(System.getenv().getOrDefault("CP_MACH", "0.3"));
		File[] orks = new File(System.getenv("CP_ORK_DIR")).listFiles((d, n) -> n.endsWith(".ork"));
		Arrays.sort(orks);
		try (PrintWriter pw = new PrintWriter(new FileWriter(System.getenv("CP_OUT")))) {
			pw.println("rocket\taoa_deg\tcp_reported\tweight_reported\tCN\tCm_nose\tcp_consistent\tcg_launch\tcg_burnout\tref_len");
			for (File ork : orks) {
				OpenRocketDocument doc = new GeneralRocketLoader(ork).load();
				Simulation sim = doc.getSimulations().get(0);
				FlightConfiguration config = doc.getRocket().getFlightConfiguration(sim.getFlightConfigurationId());
				double cgLaunch = MassCalculator.calculateLaunch(config).getCM().getX();
				double cgBurnout = MassCalculator.calculateBurnout(config).getCM().getX();
				BarrowmanCalculator calc = new BarrowmanCalculator();
				String name = ork.getName().replace(".ork", "").replace(' ', '_');
				for (int deg = 1; deg <= 90; deg += (deg == 1 ? 1 : 2)) {
					FlightConditions cond = new FlightConditions(config);
					cond.setMach(mach);
					cond.setAOA(Math.toRadians(deg));
					AerodynamicForces f = calc.getAerodynamicForces(config, cond, new WarningSet());
					double cpRep = f.getCP().getX();
					double w = f.getCP().getWeight();
					double cn = f.getCN();
					double cm = f.getCm();
					double cpCons = Math.abs(cn) > 1e-12 ? cm * cond.getRefLength() / cn : Double.NaN;
					pw.println(String.format(Locale.ROOT, "%s\t%d\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f",
							name, deg, cpRep, w, cn, cm, cpCons, cgLaunch, cgBurnout, cond.getRefLength()));
				}
			}
		}
	}
}
