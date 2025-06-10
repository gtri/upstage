# Changelog

## v0.3.2

* Knowledge events are cancelled and cleared from knowledge on interrupt
* Non-recording stores no longer break data collection

## v0.3.1

Update for critical behavior matching to SimPy in the monitoring stores and containers.

## v0.3.0

The biggest change is a behavior change that would break any sim written
in the previous version that had the inconsistent behavior. This is bringing
`Wait` and other UPSTAGE events in line with SimPy behavior for re-yielding.
The rest of the changes are non-breaking improvements to data logging,
error checking, and other features.

* `States` can now be `None` by default using parameter `allow_none_default` #31
* Utilities for bulk knowledge changing (get, set, and clear) #32
* Improved `Task` documentation and error checking #36  
* Data utility improvements (#38 , #43 )
  * `record_state()` added to record states that are objects with their own get
  and set (not just int/str/float, e.g.)
  * States with key:value attributes (like dict, dataclass, counter) get recorded
  in `create_table` by attribute
  * States that are non-recording can have their last value output to the data table
* SimPy matching behaviors in Wait (#42 )
  * Wait, and other events, weren't able to be yielded again and have behavior
  consistent with SimPy
  * Now re-yielding on a Wait will succeed on the original time
* Tailorable `DecisionTask` zero-time behavior and docs (#44 )
* Updated pixi and envs

## v0.2.1

* States now initialize to their default value on actor creation (#23)
  * Fixes a bug in data recording
  * Required improvements in `DetectabilityState` made to avoid early `MotionManager` call
* Location data object improvements. (#24)
  * The `<>LocationData` types can now test for equality. Useful for
  tests in serializing or other data pre-processing to a sim.

## v0.2.0

* Updating NamedEntity and Monitoring resources to assist data gathering.
* Added data gathering functions.
* Docs for data gathering. Updates for usability and clarity.
