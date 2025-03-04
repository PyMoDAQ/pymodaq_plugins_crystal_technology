from pymodaq.control_modules.move_utility_classes import DAQ_Move_base, comon_parameters_fun, main  # common set of parameters for all actuators
from pymodaq_gui.parameter import Parameter

from pymodaq_plugins_crystal_technology.hardware.aods_controller import AOTF, Channel, calib_ids


class DAQ_Move_AOTF(DAQ_Move_base):
    """Plugin for the AOTF Instrument

    This object inherits all functionality to communicate with PyMoDAQ Module through inheritance via DAQ_Move_base
    It then implements the particular communication with the instrument

    Attributes:
    -----------
    controller: object
        The particular object that allow the communication with the hardware, in general a python wrapper around the
         hardware library
    """
    _controller_units = 'nm' #here the units could be either a wavelength in nm or a percentage to set the amplitude
    is_multiaxes = True
    axes_names = [str(ind) for ind in range(8)]  # There are 8 channels controllable by the controller
    _epsilon = 0.01
    params = [{'title': 'Info:', 'name': 'info', 'type': 'str', 'value': '', 'readonly': True},
              {'title': 'Calibration ID:', 'name': 'calib_id', 'type': 'list', 'values': calib_ids},
              {'title': 'Selected parameter:', 'name': 'select', 'type': 'list', 'values': ['wavelength', 'amplitude']},
              {'title': 'Status:', 'name': 'status', 'type': 'group', 'children': [
                  {'title': 'Wavelength (nm):', 'name': 'wavelength', 'type': 'float', 'value': None},
                  {'title': 'Amplitude (%):', 'name': 'amplitude', 'type': 'float', 'value': 0.},
                  {'title': 'Output:', 'name': 'output', 'type': 'led_push', 'value': False},
              ]}
              ] + comon_parameters_fun(is_multiaxes, axes_names, _epsilon)

    def ini_attributes(self):
        self.controller: AOTF = None
        self._channel: Channel = None

    def get_actuator_value(self):
        """Get the current value from the hardware with scaling conversion.

        Returns
        -------
        float: The position obtained after scaling conversion.
        """
        self.settings.child('status', 'wavelength').setValue(self._channel.wavelength)
        self.settings.child('status', 'amplitude').setValue(self._channel.amplitude)
        pos = getattr(self._channel, self.settings['select'])
        pos = self.get_position_with_scaling(pos)
        return pos

    def close(self):
        """Terminate the communication protocol"""
        self.controller.close()

    def commit_settings(self, param: Parameter):
        """Apply the consequences of a change of value in the detector settings

        Parameters
        ----------
        param: Parameter
            A given parameter (within detector_settings) whose value has been changed by the user
        """
        if param.name() == "axis":
           self._channel = self.controller.get_channel(int(param.value()))
        elif param.name() == 'output':
            if not param.value():
                self._channel.amplitude = 0.
            else:
                self._channel.amplitude = self.settings['status', 'amplitude']
        elif param.name() == 'calib_id':
            self.controller.calibration = param.value()
        elif param.name() == 'wavelength':
            self._channel.wavelength = param.value()
        elif param.name() == 'amplitude':
            self._channel.amplitude = param.value() if self.settings['status', 'output'] else 0.

    def ini_stage(self, controller=None):
        """Actuator communication initialization

        Parameters
        ----------
        controller: (object)
            custom object of a PyMoDAQ plugin (Slave case). None if only one actuator by controller (Master case)

        Returns
        -------
        info: str
        initialized: bool
            False if initialization failed otherwise True
        """
        self.ini_stage_init(old_controller=controller,
                            new_controller=AOTF())
        self.controller.open(0)
        self._channel = self.controller.get_channel(int(self.settings['multiaxes', 'axis']))
        self.controller.calibration = self.settings['calib_id']

        info = f'Serial: {self.controller.get_serial()}, date: {self.controller.get_date()}'
        self.settings.child('info').setValue(info)
        initialized = True
        return info, initialized

    def move_abs(self, value):
        """ Move the actuator to the absolute target defined by value

        Parameters
        ----------
        value: (float) value of the absolute target positioning
        """

        value = self.check_bound(value)  #if user checked bounds, the defined bounds are applied here
        self.target_value = value
        value = self.set_position_with_scaling(value)  # apply scaling if the user specified one

        if self.settings['status', 'output']:
            setattr(self._channel, self.settings['select'], value)

    def move_rel(self, value):
        """ Move the actuator to the relative target actuator value defined by value

        Parameters
        ----------
        value: (float) value of the relative target positioning
        """
        value = self.check_bound(self.current_position + value) - self.current_position
        self.target_value = value + self.current_position
        value = self.set_position_relative_with_scaling(value)
        self.move_abs(self.target_value)

    def move_home(self):
        """Call the reference method of the controller"""
        self.move_abs(0.)

    def stop_motion(self):
        """Stop the actuator and emits move_done signal"""
        pass


if __name__ == '__main__':
    main(__file__, init=False)
