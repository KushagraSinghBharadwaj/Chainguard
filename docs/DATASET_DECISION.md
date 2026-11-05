# Task 4.1 decision (5 Nov 2026)

Labels are built from our own stored OFAC SDN and ScamSniffer lists. No third-party dataset is used.
Non-listed addresses are UNLABELED, not clean. GoPlus is a runtime check only and is not used as a label
(it lists ScamSniffer as a source, so it is not independent). List membership is never a model feature.
Splits are by time. The model estimates resemblance to listed addresses; it never claims fraud or safety.
Open: GPL position on ScamSniffer data has not been reviewed by a lawyer.
