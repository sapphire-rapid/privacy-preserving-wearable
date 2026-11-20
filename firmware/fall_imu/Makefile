APPLICATION = fall_imu

BOARD ?= seeedstudio-xiao-nrf52840-sense

RIOTBASE ?= $(HOME)/riotproject

# Sensor + timers
USEMODULE += lsm6dsxx
USEMODULE += ztimer
USEMODULE += ztimer_msec
USEMODULE += ztimer_usec

# Serial menu: stdio_cdc_acm is the board default and pulls in `stdin` and
# `stdio_available` by itself (makefiles/stdio.inc.mk); nothing to add for input.
# newlib-nano needs this for %f / %g in printf (adds ~ 10 kB flash)
USEMODULE += printf_float

INCLUDES += -I$(CURDIR)/include

# main thread runs the menu + all modes (printf with floats)
CFLAGS += -DTHREAD_STACKSIZE_MAIN=6144

# build id printed by the 'i' command
APP_GIT_REV := $(shell git -C $(CURDIR) describe --always --dirty 2>/dev/null || echo unknown)
CFLAGS += -DAPP_GIT_REV=\"$(APP_GIT_REV)\"

DEVELHELP ?= 1

include $(RIOTBASE)/Makefile.include
