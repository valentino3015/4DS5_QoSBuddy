-- phpMyAdmin SQL Dump
-- version 5.2.0
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1
-- Generation Time: Feb 21, 2026 at 03:01 PM
-- Server version: 10.4.24-MariaDB
-- PHP Version: 8.1.6

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `network_qos_db`
--

-- --------------------------------------------------------

--
-- Table structure for table `network_metrics`
--

CREATE TABLE `network_metrics` (
  `timestamp` varchar(255) NOT NULL,
  `source_ip` varchar(255) NOT NULL,
  `destination_ip` varchar(255) NOT NULL,
  `avg_rtt` varchar(255) NOT NULL,
  `p95_rtt` varchar(255) NOT NULL,
  `jitter` varchar(255) NOT NULL,
  `packet_loss` varchar(255) NOT NULL,
  `throughput_down` varchar(255) NOT NULL,
  `throughput_up` varchar(255) NOT NULL,
  `bandwidth_utilization` varchar(255) NOT NULL,
  `retransmission_rate` varchar(255) NOT NULL,
  `http_error_rate` varchar(255) NOT NULL,
  `availability` varchar(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

--
-- Dumping data for table `network_metrics`
--

INSERT INTO `network_metrics` (`timestamp`, `source_ip`, `destination_ip`, `avg_rtt`, `p95_rtt`, `jitter`, `packet_loss`, `throughput_down`, `throughput_up`, `bandwidth_utilization`, `retransmission_rate`, `http_error_rate`, `availability`) VALUES
('2026-02-21 15:01:40', '192.168.1.13', '8.8.8.8', '22.12', '26.13', '2.08', '0.00', '38.63', '435.66', '2.32', '0.00', '0.00', '100.00'),
('2026-02-21 15:01:47', '192.168.1.13', '8.8.8.8', '23.03', '28.19', '1.64', '0.00', '75.03', '391.94', '2.28', '0.00', '0.00', '100.00');
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;

-- BO1 Raw Metrics Table
CREATE TABLE IF NOT EXISTS qos_metrics_raw (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp VARCHAR(32) NOT NULL,
    window_id INT NOT NULL,
    avg_rtt_ms FLOAT NULL,
    jitter_ms FLOAT NULL,
    packet_loss_pct FLOAT NULL,
    throughput_up_mbps FLOAT NULL,
    throughput_down_mbps FLOAT NULL,
    retransmission_rate_pct FLOAT NULL,
    dns_time_ms FLOAT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
