APPLICATION = fall_imu

BOARD ?= seeedstudio-xiao-nrf52840-sense

RIOTBASE ?= $(CURDIR)/../../riotproject

# Sensor + timers
USEMODULE += lsm6dsxx
USEMODULE += ztimer
USEMODULE += ztimer_msec
USEMODULE += ztimer_usec

INCLUDES += -I$(CURDIR)/include

DEVELHELP ?= 1

include $(RIOTBASE)/Makefile.include
