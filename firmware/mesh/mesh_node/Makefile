APPLICATION = mesh_node

BOARD ?= seeedstudio-xiao-nrf52840-sense
RIOTBASE ?= $(HOME)/riotproject

# ROLE=hr    -> MAX30102 heart-rate node, sends {seq,bpm,rank} every 3 s, prints ACKs
# ROLE=relay -> plain RPL router, sends a heartbeat every 10 s, prints ACKs
ROLE ?= relay

ifeq (hr,$(ROLE))
  CFLAGS += -DMESH_ROLE_HR=1
  USEMODULE += periph_i2c
else ifeq (relay,$(ROLE))
  CFLAGS += -DMESH_ROLE_HR=0
else
  $(error ROLE must be 'hr' or 'relay')
endif

# Separate bin dir per role so 'make ROLE=hr' and 'make ROLE=relay' never mix objects
BINDIR ?= $(CURDIR)/bin/$(BOARD)-$(ROLE)

include $(CURDIR)/../rpl_tuning.mk

USEMODULE += netdev_default
USEMODULE += auto_init_gnrc_netif
USEMODULE += gnrc_icmpv6_error
USEMODULE += gnrc_icmpv6_echo
USEMODULE += gnrc_ipv6_router_default
USEMODULE += gnrc_rpl
USEMODULE += auto_init_gnrc_rpl
USEMODULE += gnrc_sock_udp
USEMODULE += ztimer_msec

DEVELHELP ?= 1

include $(RIOTBASE)/Makefile.include
include $(RIOTMAKE)/default-radio-settings.inc.mk
