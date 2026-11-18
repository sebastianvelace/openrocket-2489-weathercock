package info.openrocket.core.simulation;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Locale;
import java.util.Map;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import info.openrocket.core.aerodynamics.AerodynamicForces;
import info.openrocket.core.aerodynamics.BarrowmanCalculator;
import info.openrocket.core.aerodynamics.FlightConditions;
import info.openrocket.core.logging.WarningSet;
import info.openrocket.core.file.GeneralRocketLoader;
import info.openrocket.core.rocketcomponent.FinSet;
import info.openrocket.core.rocketcomponent.FlightConfiguration;
import info.openrocket.core.rocketcomponent.Rocket;
import info.openrocket.core.rocketcomponent.RocketComponent;
import info.openrocket.core.rocketcomponent.SymmetricComponent;
import info.openrocket.core.util.BaseTestCase;

/**
 * Throwaway probe for issue #2489: static normal force and CP of the TRF rocket versus angle of attack,
 * split into body (symmetric components) and fins. Env: SA_ORK, SA_OUT, SA_LABEL, SA_MACH.
 */
public class StaticAeroProbeTest extends BaseTestCase {

	@BeforeAll
	public static void loadDatabases() throws Exception {
		info.openrocket.core.file.openrocket.ExampleFilesTest.setUp();
	}

	@Test
	public void sweep() throws Exception {
		Rocket rocket = new GeneralRocketLoader(new File(System.getenv("SA_ORK"))).load().getRocket();
		FlightConfiguration config = rocket.getSelectedConfiguration();
		for (String machStr : System.getenv().getOrDefault("SA_MACH", "0.1").split(",")) {
		double mach = Double.parseDouble(machStr);
		BarrowmanCalculator calc = new BarrowmanCalculator();
		File out = new File(System.getenv("SA_OUT"), System.getenv().getOrDefault("SA_LABEL", "static") + "_M" + machStr + ".tsv");
		out.getParentFile().mkdirs();
		try (PrintWriter pw = new PrintWriter(new FileWriter(out))) {
			pw.println("aoa_deg\tCN_total\tCP_total_m\tCN_body\tCm_body_nose\tCN_fins\tCP_fins_m\tref_area\tref_len");
			for (int deg = 0; deg <= 40; deg += 2) {
				FlightConditions cond = new FlightConditions(config);
				cond.setMach(mach);
				cond.setAOA(Math.toRadians(Math.max(deg, 1e-6)));
				Map<RocketComponent, AerodynamicForces> map = calc.getForceAnalysis(config, cond, new WarningSet());
				double cnBody = 0, cmBody = 0, cnFins = 0, cpFins = Double.NaN;
				for (Map.Entry<RocketComponent, AerodynamicForces> e : map.entrySet()) {
					AerodynamicForces f = e.getValue();
					if (e.getKey() instanceof SymmetricComponent) {
						cnBody += f.getCN();
						// moment about the nose tip: CN * absolute CP x / ref length
						double xAbs = f.getCP().getX() + e.getKey().getComponentLocations()[0].getX();
						cmBody += f.getCN() * xAbs / cond.getRefLength();
					} else if (e.getKey() instanceof FinSet) {
						cnFins += f.getCN();
						cpFins = f.getCP().getX() + e.getKey().getComponentLocations()[0].getX();
					}
				}
				double cpTotal = calc.getCP(config, cond, new WarningSet()).getX();
				AerodynamicForces tot = calc.getAerodynamicForces(config, cond, new WarningSet());
				pw.println(String.format(Locale.ROOT, "%d\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\t%.8f\t%.6f", deg,
						tot.getCN(), cpTotal, cnBody, cmBody, cnFins, cpFins, cond.getRefArea(), cond.getRefLength()));
			}
		}
		}
	}
}
