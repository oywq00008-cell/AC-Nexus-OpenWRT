include $(TOPDIR)/rules.mk

PKG_NAME:=acnexus
PKG_VERSION:=3.2
PKG_RELEASE:=1
PKG_LICENSE:=MIT
PKG_MAINTAINER:=oywq00008-cell

include $(INCLUDE_DIR)/package.mk

define Package/acnexus
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=AC-Nexus-OpenWRT — AI Smart AC Controller
  DEPENDS:=+python3-light +python3-urllib +python3-email +python3-openssl +python3-xml
  # broadlink / schedule / pyaes 已内置到 /usr/lib/acnexus/ 无需 opkg
  URL:=https://github.com/oywq00008-cell/AC-Nexus-OpenWRT
endef

define Package/acnexus/description
  AI-powered smart AC controller for IR blasters (Broadlink RM + Xiaomi MIoT).
  Supports 17 AC brands, dual weather sources, NMC/NHC typhoon & hurricane tracking,
  and automatic shutdown on storm approach.
endef

define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)
	$(CP) ./files/* $(PKG_BUILD_DIR)/
endef

define Build/Compile
	true
endef

define Package/acnexus/install
	$(INSTALL_DIR) $(1)/etc/config
	$(CP) $(PKG_BUILD_DIR)/etc/config/acnexus $(1)/etc/config/

	$(INSTALL_DIR) $(1)/etc/uci-defaults
	$(CP) $(PKG_BUILD_DIR)/etc/uci-defaults/99-acnexus $(1)/etc/uci-defaults/

	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/etc/init.d/acnexus $(1)/etc/init.d/

	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/controller
	$(CP) $(PKG_BUILD_DIR)/usr/lib/lua/luci/controller/acnexus.lua $(1)/usr/lib/lua/luci/controller/

	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/model/cbi
	$(CP) $(PKG_BUILD_DIR)/usr/lib/lua/luci/model/cbi/acnexus.lua $(1)/usr/lib/lua/luci/model/cbi/

	$(INSTALL_DIR) $(1)/usr/lib/acnexus
	$(CP) $(PKG_BUILD_DIR)/usr/lib/acnexus/*.py $(1)/usr/lib/acnexus/
	$(CP) -r $(PKG_BUILD_DIR)/usr/lib/acnexus/acnexus_core $(1)/usr/lib/acnexus/
	$(CP) -r $(PKG_BUILD_DIR)/usr/lib/acnexus/protocols $(1)/usr/lib/acnexus/
	$(CP) -r $(PKG_BUILD_DIR)/usr/lib/acnexus/broadlink $(1)/usr/lib/acnexus/
	$(CP) -r $(PKG_BUILD_DIR)/usr/lib/acnexus/pyaes $(1)/usr/lib/acnexus/
	$(CP) -r $(PKG_BUILD_DIR)/usr/lib/acnexus/schedule $(1)/usr/lib/acnexus/
	$(CP) -r $(PKG_BUILD_DIR)/usr/lib/acnexus/hvac_ir $(1)/usr/lib/acnexus/
endef

$(eval $(call BuildPackage,acnexus))
