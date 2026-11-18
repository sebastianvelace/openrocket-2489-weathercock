package info.openrocket.core.aerodynamics;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import info.openrocket.core.logging.WarningSet;
import info.openrocket.core.rocketcomponent.FlightConfiguration;
import info.openrocket.core.rocketcomponent.Rocket;
import info.openrocket.core.util.BaseTestCase;
import info.openrocket.core.util.TestRockets;

/**
 * The reported center of pressure must be where the summed normal force acts: CP = Cm * Lref / CN.
 * Below the fin stall angle this holds; above it the fin CP weight stays at the uncapped CNa while the
 * fin normal force is capped, and the two diverge.
 */
public class CPForceConsistencyTest extends BaseTestCase {

	@ParameterizedTest(name = "AoA {0} deg")
	@ValueSource(doubles = { 5, 10, 15, 25, 40, 60, 80 })
	public void reportedCPMatchesSummedForces(double aoaDeg) {
		Rocket rocket = TestRockets.makeEstesAlphaIII();
		FlightConfiguration config = rocket.getSelectedConfiguration();
		FlightConditions conditions = new FlightConditions(config);
		conditions.setMach(0.3);
		conditions.setAOA(Math.toRadians(aoaDeg));

		AerodynamicForces forces = new BarrowmanCalculator().getAerodynamicForces(config, conditions, new WarningSet());

		double cpFromForces = forces.getCm() * conditions.getRefLength() / forces.getCN();
		assertEquals(cpFromForces, forces.getCP().getX(), 1e-9,
				"reported CP must equal Cm * Lref / CN at " + aoaDeg + " deg");
	}
}
