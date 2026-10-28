# Municipality Boundary Match Registry

This registry documents the audited 1:1 corrections from GAUL-coded NTL municipalities to GeoBoundaries polygons.
Raw source files remain unchanged under `raw/`; corrected working outputs are rebuilt under `working/` and `out/`.

## Summary
- NTL municipality units: 1,211
- Matched to one polygon: 1,132
- Matched through audited aliases: 84
- Still unmatched: 79

## Match Policy
- Exact normalized country + ADM1 + ADM2 matches are retained.
- Audited aliases are retained only when one NTL unit maps to exactly one GeoBoundaries polygon.
- Placeholder, lake, island-fragment, and many-to-one cases are not forced into a polygon.

## Country Coverage
| Country/metric | NTL units | Matched | Unmatched |
|---|---:|---:|---:|
| Belize | 6 | 6 | 0 |
| Costa Rica | 81 | 75 | 6 |
| El Salvador | 262 | 241 | 21 |
| Guatemala | 336 | 331 | 5 |
| Honduras | 291 | 288 | 3 |
| Nicaragua | 158 | 130 | 28 |
| Panama | 77 | 61 | 16 |

## Audited Alias Matches
| Country | Source ADM1 | Source ADM2 | Polygon ADM1 | Polygon ADM2 | Alias Type |
|---|---|---|---|---|---|
| Guatemala | Alta Verapaz | Raxruja | Alta Verapaz | Raxruhá | ADM2 |
| Guatemala | Alta Verapaz | Santa Catarina La Tinta | Alta Verapaz | Santa Catalina La Tinta | ADM2 |
| Guatemala | Chiquimula | Quetzaltepeque | Chiquimula | Quezaltepeque | ADM2 |
| Guatemala | Chiquimula | San Juan la Ermita | Chiquimula | San Juan Ermita | ADM2 |
| Guatemala | El Progreso | San Cristóbal Acasguastlan | El Progreso | San Cristóbal Acasaguastlán | ADM2 |
| Guatemala | Escuintla | Santa Lucia Cotzulmalguapa | Escuintla | Santa Lucía Cotzumalguapa | ADM2 |
| Guatemala | Guatemala | San Raymundo | Guatemala | San Raimundo | ADM2 |
| Guatemala | Huehuetenango | San Idelfonso Ixtahuacán | Huehuetenango | Ixtahuacán | ADM2 |
| Guatemala | Quetzaltenango | San Juan Ostuncalco | Quetzaltenango | Ostuncalco | ADM2 |
| Guatemala | Retalhuleu | San Felipe Retalhuleu | Retalhuleu | San Felipe | ADM2 |
| Guatemala | Sololá | San Antonio Palapó | Sololá | San Antonio Palopó | ADM2 |
| Guatemala | Sololá | Santa Catarina Palapó | Sololá | Santa Catarina Palopó | ADM2 |
| Guatemala | Suchitepéquez | San Bernandino | Suchitepéquez | San Bernardino | ADM2 |
| Guatemala | Suchitepéquez | San Pablo Jocopila | Suchitepéquez | San Pablo Jocopilas | ADM2 |
| Guatemala | Totonicapán | San Bartolo Aguas Calientes | Totonicapán | San Bartolo | ADM2 |
| Honduras | Comayagua | Ojo De Agua | Comayagua | Ojos de Agua | ADM2 |
| Honduras | Copan | Cabanas | Copán | Cabana | ADM2 |
| Honduras | Copan | Trinidad | Copán | Trinidad de Copan | ADM2 |
| Honduras | Islas De Bahia | Guanaja | Bay Islands | Guanaja | ADM1 |
| Honduras | Islas De Bahia | Jose Santos Guardiola | Bay Islands | Jose Santos Guardiola | ADM1 |
| Honduras | Islas De Bahia | Roatan | Bay Islands | Roatan | ADM1 |
| Honduras | Islas De Bahia | Utila | Bay Islands | Utila | ADM1 |
| Honduras | Lempira | San Manuel Del Colohete | Lempira | San Manuel Colohete | ADM2 |
| Honduras | Ocotepeque | Nueva Ocotepeque | Ocotepeque | Ocotepeque | ADM2 |
| Honduras | Paraiso | Alauca | El Paraíso | Alauca | ADM1 |
| Honduras | Paraiso | Danli | El Paraíso | Danli | ADM1 |
| Honduras | Paraiso | El Paraiso | El Paraíso | El Paraiso | ADM1 |
| Honduras | Paraiso | Guinope | El Paraíso | Guinope | ADM1 |
| Honduras | Paraiso | Jacaleapa | El Paraíso | Jacaleapa | ADM1 |
| Honduras | Paraiso | Liure | El Paraíso | Liure | ADM1 |
| Honduras | Paraiso | Moroceli | El Paraíso | Moroceli | ADM1 |
| Honduras | Paraiso | Oropoli | El Paraíso | Oropoli | ADM1 |
| Honduras | Paraiso | Potrerillos | El Paraíso | Potrerillos | ADM1 |
| Honduras | Paraiso | San Antonio De Flores | El Paraíso | San Antonio de Flores | ADM1 |
| Honduras | Paraiso | San Lucas | El Paraíso | San Lucas | ADM1 |
| Honduras | Paraiso | San Matias | El Paraíso | San Matias | ADM1 |
| Honduras | Paraiso | Soledad | El Paraíso | Soledad | ADM1 |
| Honduras | Paraiso | Teupasenti | El Paraíso | Teupasenti | ADM1 |
| Honduras | Paraiso | Texiguat | El Paraíso | Texiguat | ADM1 |
| Honduras | Paraiso | Vado Ancho | El Paraíso | Vado Ancho | ADM1 |
| Honduras | Paraiso | Yauyupe | El Paraíso | Yauyupe | ADM1 |
| Honduras | Paraiso | Yuscaran | El Paraíso | Yuscaran | ADM1 |
| Honduras | Santa Barbara | San Jose De Colimas | Santa Bárbara | San Jose de Colinas | ADM2 |
| Nicaragua | Atlantico Norte | Bonanza | North Carribean Coast Autonomous Region | Municipio Bonanza | ADM1 |
| Nicaragua | Atlantico Norte | Prinzapolka | North Carribean Coast Autonomous Region | Municipio Prinzapolka | ADM1 |
| Nicaragua | Atlantico Norte | Puerto Cabezas | North Carribean Coast Autonomous Region | Municipio Puerto Cabezas | ADM1 |
| Nicaragua | Atlantico Norte | Rosita | North Carribean Coast Autonomous Region | Municipio Rosita | ADM1 |
| Nicaragua | Atlantico Norte | Siuna | North Carribean Coast Autonomous Region | Municipio Siuna | ADM1 |
| Nicaragua | Atlantico Norte | Waslala | North Carribean Coast Autonomous Region | Municipio Waslala | ADM1 |
| Nicaragua | Atlantico Norte | Waspam | North Carribean Coast Autonomous Region | Municipio Waspán | ADM1, ADM2 |
| Nicaragua | Atlantico Sur | Bluefields | South Atlantic Autonomous Region | Municipio Bluefields | ADM1 |
| Nicaragua | Atlantico Sur | Bocanas De Paiwa | South Atlantic Autonomous Region | Municipio El Ayote | ADM1, ADM2 |
| Nicaragua | Atlantico Sur | El  Rama | South Atlantic Autonomous Region | Municipio El Rama | ADM1 |
| Nicaragua | Atlantico Sur | Kukra Hill | South Atlantic Autonomous Region | Municipio Kukra Hill | ADM1 |
| Nicaragua | Atlantico Sur | La Cruz De Rio Grande | South Atlantic Autonomous Region | Municipio La Cruz de Río Grande | ADM1 |
| Nicaragua | Atlantico Sur | Muelle De Los Bueyes | South Atlantic Autonomous Region | Municipio Muelle de los Bueyes | ADM1 |
| Nicaragua | Atlantico Sur | Nueva Guinea | South Atlantic Autonomous Region | Municipio Nueva Guinea | ADM1 |
| Nicaragua | Chinandega | Cinco Pinos | Chinandega | San Juan de Cinco Pinos (Municipio) | ADM2 |
| Nicaragua | Chinandega | San Fco. Del Norte | Chinandega | San Francisco del Norte (Municipio) | ADM2 |
| Nicaragua | Esteli | Plueblo Nuevo | Estelí | Municipio Pueblo Nuevo | ADM2 |
| Nicaragua | Jinotega | Jinotega | Jinotega (Departamento) | Municipio de Jinotega | ADM2 |
| Nicaragua | Jinotega | San Sebastian De Yali | Jinotega (Departamento) | Muncipio San Sebastián de Yalí | ADM2 |
| Nicaragua | Jinotega | Wiwili | Jinotega (Departamento) | Municipio Wiwilí de Jinotega | ADM2 |
| Nicaragua | Leon | Malpaisillo | Leon | Municipio Larreynaga | ADM2 |
| Nicaragua | Madriz | San Juan Del Rio Coco | Madriz | Municipio San Juan de Río Coco | ADM2 |
| Nicaragua | Madriz | Totolgalpa | Madriz | Totogalpa (Municipio) | ADM2 |
| Nicaragua | Managua | Villa Carlos Fonseca A | Managua | Villa El Carmen (Municipio) | ADM2 |
| Nicaragua | Masaya | Nandasmo | Masaya | Nandasmo (Muncipio) | ADM2 |
| Nicaragua | Matagalpa | Ciudad Dario | Matagalpa (Departemento) | Municipio Ciudad Darco | ADM1, ADM2 |
| Nicaragua | Matagalpa | Esquipulas | Matagalpa (Departemento) | Municipio Esquipulas | ADM1 |
| Nicaragua | Matagalpa | La Dalia | Matagalpa (Departemento) | Municipio El Tuma - La Dalia | ADM1, ADM2 |
| Nicaragua | Matagalpa | Matagalpa | Matagalpa (Departemento) | Municipio Matagalpa | ADM1 |
| Nicaragua | Matagalpa | Matiguas | Matagalpa (Departemento) | Municipio Matiguás | ADM1 |
| Nicaragua | Matagalpa | Muy Muy | Matagalpa (Departemento) | Municipio Muy Muy | ADM1 |
| Nicaragua | Matagalpa | Rancho Grande | Matagalpa (Departemento) | Municipio Rancho Grande | ADM1 |
| Nicaragua | Matagalpa | Rio Blanco | Matagalpa (Departemento) | Municipio Río Blanco | ADM1 |
| Nicaragua | Matagalpa | San Dionisio | Matagalpa (Departemento) | Municipio San Dionisio | ADM1 |
| Nicaragua | Matagalpa | San Isidro | Matagalpa (Departemento) | Municipio San Isidro | ADM1 |
| Nicaragua | Matagalpa | San Ramon | Matagalpa (Departemento) | Municipio San Ramon | ADM1 |
| Nicaragua | Matagalpa | Sebaco | Matagalpa (Departemento) | Municipio Sebaco | ADM1 |
| Nicaragua | Matagalpa | Terrabona | Matagalpa (Departemento) | Municipio Terrabona | ADM1 |
| Nicaragua | Nueva Segovia | Dipilto | Nueva Segovia | Municipio Dipilito | ADM2 |
| Nicaragua | Nueva Segovia | Mosonte | Nueva Segovia | Municipio Monzonte | ADM2 |
| Nicaragua | Rivas | Moyogalpa | Rivas | Moyagalpa (Muncipio) | ADM2 |

## Still Unmatched / Not Forced
| Country | ADM1 | ADM2 | Reason |
|---|---|---|---|
| Costa Rica | Alajuela | Alfaro Ruiz | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Costa Rica | Alajuela | Palmares | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Costa Rica | Alajuela | Valverde Vega | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Costa Rica | Puntarenas | Aguirre | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Costa Rica | San Jose | Leon Cortes | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Costa Rica | San Jose | Vasquez De Coronado | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | Ahuachapan | Ahuachapan | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | Cabanas | Guacotecti | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | Cabanas | Ilobasco | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | Cabanas | Tejutepeque | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | Chalatenango | Cancasque | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | Chalatenango | Chalatenango | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | Chalatenango | Las Flores | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | Chalatenango | San Antonio Los Ranchos | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | Chalatenango | San Ignacio | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | La Libertad | Sacacoyo | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | La Libertad | San Juan Opico | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | La Paz | Jerusalen | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | La Paz | San Emigdio | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | La Paz | San Francisco Chinameca | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | La Union | Meanguera Del Golfo | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | Morazan | Chilanga | Alias is not accepted because it does not point to exactly one GeoBoundaries polygon. |
| El Salvador | Morazan | San Francisco Gotera | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | San Miguel | San Rafael Oriente | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | Sonsonate | Santo Domingo De Guzman | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | Sonsonate | Sonzacate | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| El Salvador | Usulutan | San Buena Ventura | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Guatemala | Guatemala | Lago de Amatitlán | Water body / lake unit in the NTL source; GeoBoundaries municipality polygons do not contain a 1:1 lake municipality. |
| Guatemala | Izabal | Administrative unit not available | No named municipality polygon in GeoBoundaries; placeholder unit is not a defensible 1:1 polygon. |
| Guatemala | Sololá | Lago de Atitlán | Water body / lake unit in the NTL source; GeoBoundaries municipality polygons do not contain a 1:1 lake municipality. |
| Guatemala | Suchitepéquez | Pueblo Nuevo | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Guatemala | Suchitepéquez | Río Bravo | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Honduras | Francisco Morazan | Santa  Ana | Alias is not accepted because multiple NTL units would map to the same polygon. |
| Honduras | Francisco Morazan | Santa Ana | Alias is not accepted because multiple NTL units would map to the same polygon. |
| Honduras | Name Unknown | Name Unknown | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Nicaragua | Atlantico Norte | Sunbeam | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Nicaragua | Atlantico Sur | Great Corn Island | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Atlantico Sur | Isla | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Atlantico Sur | Little Corn Island | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Boaco | Administrative unit not available | No named municipality polygon in GeoBoundaries; placeholder unit is not a defensible 1:1 polygon. |
| Nicaragua | Chinandega | Isla | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Chinandega | Isla Mangles Altos | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Chinandega | Tonala | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Nicaragua | Chontales | Administrative unit not available | No named municipality polygon in GeoBoundaries; placeholder unit is not a defensible 1:1 polygon. |
| Nicaragua | Chontales | Isla El Muerto | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Chontales | Isla Grade | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Chontales | Isla Redonda | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Chontales | Islas El Nancital | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Granada | Administrative unit not available | No named municipality polygon in GeoBoundaries; placeholder unit is not a defensible 1:1 polygon. |
| Nicaragua | Granada | Isla Las Calabazas | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Granada | Isla Zapatera | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Jinotega | Las Praderas | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Nicaragua | Nueva Segovia | Ciudad Sandino | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Nicaragua | Rio San Juan | Administrative unit not available | No named municipality polygon in GeoBoundaries; placeholder unit is not a defensible 1:1 polygon. |
| Nicaragua | Rio San Juan | Isla Chichicaste | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Rio San Juan | Isla El Zapote | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Rio San Juan | Isla La Venada | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Rio San Juan | Isla Mancarron | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Rio San Juan | Isla Mancarroncito | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Rio San Juan | Isla San Fernando | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Rio San Juan | Islas San Bernardo | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Nicaragua | Rivas | Administrative unit not available | No named municipality polygon in GeoBoundaries; placeholder unit is not a defensible 1:1 polygon. |
| Nicaragua | Rivas | Isla | Island/islet unit without a unique municipality polygon, or split into pieces not represented 1:1 in GeoBoundaries. |
| Panama | Darién | Kuna de Wargandí | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Panama | Emberá | Cémaco | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Panama | Emberá | Sambú | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Panama | Ngöbe Buglé | Besiko | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Panama | Ngöbe Buglé | Kankintú | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Panama | Ngöbe Buglé | Kusapín | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Panama | Ngöbe Buglé | Mironó | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Panama | Ngöbe Buglé | Müna | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Panama | Ngöbe Buglé | Nole Duima | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Panama | Ngöbe Buglé | Ñürüm | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Panama | Panamá | Arraiján | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Panama | Panamá | Capira | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Panama | Panamá | Chame | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Panama | Panamá | Kuna de Madungandí | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Panama | Panamá | La Chorrera | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
| Panama | Panamá | San Carlos | No conservative 1:1 polygon match found in GeoBoundaries after audited aliases. |
