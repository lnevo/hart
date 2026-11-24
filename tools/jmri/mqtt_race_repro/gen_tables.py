import sys
n = int(sys.argv[1])
out = ['<?xml version="1.0" encoding="UTF-8"?>',
 '<layout-config xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://jmri.org/xml/schema/layout-5-5-5.xsd">',
 '  <sensors class="jmri.jmrix.mqtt.configurexml.MqttSensorManagerXml">']
for i in range(1, n+1):
    out.append(f'    <sensor inverted="false"><systemName>MS{i}</systemName></sensor>')
out.append('  </sensors>')
out.append('  <turnouts class="jmri.jmrix.mqtt.configurexml.MqttTurnoutManagerXml">')
for i in range(1, n+1):
    out.append(f'    <turnout feedback="DIRECT" inverted="false" automate="Off"><systemName>MT{i}</systemName></turnout>')
out.append('  </turnouts>')
out.append('</layout-config>')
print("\n".join(out))
