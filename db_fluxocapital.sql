-- MariaDB dump 10.19-12.2.2-MariaDB, for osx10.21 (arm64)
--
-- Host: localhost    Database: db_fluxocapital
-- ------------------------------------------------------
-- Server version	12.2.2-MariaDB

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*M!100616 SET @OLD_NOTE_VERBOSITY=@@NOTE_VERBOSITY, NOTE_VERBOSITY=0 */;

--
-- Table structure for table `ativos`
--

DROP TABLE IF EXISTS `ativos`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `ativos` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `ticker` varchar(100) NOT NULL,
  `nome_ativo` varchar(100) DEFAULT NULL,
  `data_compra` date NOT NULL,
  `quantidade` decimal(18,6) NOT NULL,
  `preco_compra` decimal(15,2) NOT NULL,
  `preco_atual` decimal(15,2) DEFAULT NULL,
  `pvp` decimal(15,2) DEFAULT NULL,
  `tipo_ativo` varchar(50) DEFAULT NULL,
  `categoria` varchar(50) DEFAULT NULL,
  `carteira` varchar(50) DEFAULT 'Família',
  `categoria_id` int(11) DEFAULT NULL,
  `carteira_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_ativo_categoria_ativo` (`categoria_id`),
  KEY `fk_ativos_carteira` (`carteira_id`),
  FOREIGN KEY (`categoria_id`) REFERENCES `categoria_ativos` (`id`),
  FOREIGN KEY (`carteira_id`) REFERENCES `carteiras` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `ativos`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `ativos` WRITE;
/*!40000 ALTER TABLE `ativos` DISABLE KEYS */;
INSERT INTO `ativos` VALUES
(1,'VALE3',NULL,'2026-01-01',5.000000,72.00,78.86,1.88,NULL,'Ações','Carteira 1',1,10),
(2,'HGLG11',NULL,'2026-02-01',5.000000,155.00,158.33,0.95,NULL,'FIIs','Carteira 1',2,10),
(3,'HGLG11',NULL,'2026-03-06',5.000000,158.37,158.33,0.95,NULL,'Ações','Carteira 1',2,10),
(4,'BOVA11',NULL,'2026-03-06',6.000000,174.00,175.89,NULL,NULL,'Ações','Carteira 2',3,11),
(5,'BOVA11',NULL,'2026-03-06',10.000000,174.00,175.89,NULL,NULL,'ETFs','Carteira 2',3,11),
(6,'PETR4',NULL,'2026-03-06',10.000000,40.25,42.11,NULL,NULL,'Ações','Carteira 2',1,11),
(7,'TESOURO SELIC',NULL,'2026-03-07',1.000000,5000.00,5100.00,NULL,NULL,'Ações','Carteira 1',6,10);
/*!40000 ALTER TABLE `ativos` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `carteiras`
--

DROP TABLE IF EXISTS `carteiras`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `carteiras` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nome` varchar(50) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `nome` (`nome`)
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `carteiras`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `carteiras` WRITE;
/*!40000 ALTER TABLE `carteiras` DISABLE KEYS */;
INSERT INTO `carteiras` VALUES
(10,'Carteira 1'),
(11,'Carteira 2'),
(1,'Consolidada');
/*!40000 ALTER TABLE `carteiras` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `categoria_ativos`
--

DROP TABLE IF EXISTS `categoria_ativos`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `categoria_ativos` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nome` varchar(50) NOT NULL,
  `carteira_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `nome` (`nome`),
  KEY `fk_categoria_ativos_carteira` (`carteira_id`),
  FOREIGN KEY (`carteira_id`) REFERENCES `carteiras` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `categoria_ativos`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `categoria_ativos` WRITE;
/*!40000 ALTER TABLE `categoria_ativos` DISABLE KEYS */;
INSERT INTO `categoria_ativos` VALUES
(1,'Ações',NULL),
(2,'FIIs',NULL),
(3,'ETFs',NULL),
(4,'BDRs',NULL),
(5,'Internacional',NULL),
(6,'Renda Fixa',NULL),
(7,'Previdência',NULL),
(8,'Cripto',NULL);
/*!40000 ALTER TABLE `categoria_ativos` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `categoria_proventos`
--

DROP TABLE IF EXISTS `categoria_proventos`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `categoria_proventos` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nome` varchar(50) NOT NULL,
  `carteira_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `nome` (`nome`),
  KEY `fk_categoria_proventos_carteira` (`carteira_id`),
  FOREIGN KEY (`carteira_id`) REFERENCES `carteiras` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `categoria_proventos`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `categoria_proventos` WRITE;
/*!40000 ALTER TABLE `categoria_proventos` DISABLE KEYS */;
INSERT INTO `categoria_proventos` VALUES
(1,'Dividendos',NULL),
(2,'JCP',NULL),
(3,'Bonificação',NULL),
(4,'Rendimentos',NULL),
(5,'Juros',NULL),
(6,'Amortização',NULL),
(8,'Rendimentos BTC',NULL),
(12,'Frações de Ações',NULL);
/*!40000 ALTER TABLE `categoria_proventos` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `categorias`
--

DROP TABLE IF EXISTS `categorias`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `categorias` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nome` varchar(50) NOT NULL,
  `tipo` varchar(20) NOT NULL,
  `icone` varchar(50) DEFAULT NULL,
  `carteira_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `nome` (`nome`),
  KEY `fk_categorias_carteira` (`carteira_id`),
  FOREIGN KEY (`carteira_id`) REFERENCES `carteiras` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=22 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `categorias`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `categorias` WRITE;
/*!40000 ALTER TABLE `categorias` DISABLE KEYS */;
INSERT INTO `categorias` VALUES
(1,'Salário','Receita','bi-cash-stack',NULL),
(2,'Dividendos','Receita','bi-graph-up-arrow',NULL),
(3,'Outras Receitas','Receita','bi-plus-circle',NULL),
(4,'Alimentação','Despesa','bi-cart',NULL),
(5,'Moradia','Despesa','bi-house',NULL),
(6,'Transporte','Despesa','bi-car-front',NULL),
(7,'Lazer','Despesa','bi-airplane',NULL),
(8,'Investimento','Despesa','bi-piggy-bank',NULL),
(9,'Saúde','Despesa','bi-heart-pulse',NULL),
(10,'Impostos','Despesa','bi-receipt',NULL),
(11,'Outras Despesas','Despesa','bi-dash-circle',NULL),
(12,'Telefonia/Internet','Despesa','bi-telephone',NULL),
(13,'Cartão de Crédito','Despesa','bi-credit-card',NULL),
(14,'Educação','Despesa','bi-book',NULL),
(15,'Honorários','Receita','bi-cash-stack',NULL),
(16,'Vestuário','Despesa','bi-tag',NULL),
(17,'Casa/Decoração','Despesa','bi-tag',NULL),
(18,'Streaming','Despesa','bi-tag',NULL),
(19,'Compras Internet','Despesa','bi-tag',NULL),
(20,'Beleza/Higiene','Despesa','bi-tag',NULL),
(21,'Funcionário','Despesa','bi-tag',NULL);
/*!40000 ALTER TABLE `categorias` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `config_financeiras_fixas`
--

DROP TABLE IF EXISTS `config_financeiras_fixas`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `config_financeiras_fixas` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `descricao` varchar(255) NOT NULL,
  `valor_estimado` decimal(15,2) DEFAULT NULL,
  `dia_vencimento` int(11) DEFAULT NULL,
  `categoria_id` int(11) DEFAULT NULL,
  `carteira` varchar(50) DEFAULT NULL,
  `ativo` tinyint(1) DEFAULT NULL,
  `tipo` varchar(20) NOT NULL DEFAULT 'Despesa',
  `carteira_id` int(11) DEFAULT NULL,
  `posicao` int(11) DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `categoria_id` (`categoria_id`),
  KEY `fk_config_financeiras_fixas_carteira` (`carteira_id`),
  FOREIGN KEY (`categoria_id`) REFERENCES `categorias` (`id`),
  FOREIGN KEY (`carteira_id`) REFERENCES `carteiras` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `config_financeiras_fixas`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `config_financeiras_fixas` WRITE;
/*!40000 ALTER TABLE `config_financeiras_fixas` DISABLE KEYS */;
INSERT INTO `config_financeiras_fixas` VALUES
(1,'Diarista',1000.00,1,21,'Consolidada',1,'Despesa',1,0);
/*!40000 ALTER TABLE `config_financeiras_fixas` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `dividendos`
--

DROP TABLE IF EXISTS `dividendos`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `dividendos` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `ticker` varchar(100) NOT NULL,
  `valor_total` decimal(15,2) NOT NULL,
  `data_recebimento` date NOT NULL,
  `tipo` varchar(50) DEFAULT NULL,
  `carteira` varchar(50) DEFAULT 'Família',
  `categoria_provento_id` int(11) DEFAULT NULL,
  `carteira_id` int(11) DEFAULT NULL,
  `categoria_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_categoria_provento` (`categoria_provento_id`),
  KEY `fk_dividendos_carteira` (`carteira_id`),
  KEY `fk_div_categoria_ativo` (`categoria_id`),
  FOREIGN KEY (`categoria_provento_id`) REFERENCES `categoria_proventos` (`id`),
  FOREIGN KEY (`categoria_id`) REFERENCES `categoria_ativos` (`id`),
  FOREIGN KEY (`carteira_id`) REFERENCES `carteiras` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `dividendos`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `dividendos` WRITE;
/*!40000 ALTER TABLE `dividendos` DISABLE KEYS */;
INSERT INTO `dividendos` VALUES
(1,'VALE3',25.00,'2026-03-06','Dividendos','Carteira 1',1,10,1),
(2,'HGLG11',32.00,'2026-03-06','Rendimentos','Carteira 1',4,10,2),
(3,'BOVA11',5.00,'2026-03-06','Dividendos','Carteira 2',1,11,3),
(4,'PETR4',5.80,'2026-03-06','JCP','Carteira 2',2,11,1),
(5,'PETR4',7.50,'2026-01-06','Dividendos','Carteira 2',1,11,1),
(6,'PETR4',9.00,'2025-12-15','Dividendos','Carteira 2',1,11,1);
/*!40000 ALTER TABLE `dividendos` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `folha_pagamentos`
--

DROP TABLE IF EXISTS `folha_pagamentos`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `folha_pagamentos` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `funcionario_id` int(11) NOT NULL,
  `mes_referencia` varchar(7) NOT NULL,
  `valor_bruto` decimal(15,2) NOT NULL,
  `desconto_inss` decimal(15,2) NOT NULL,
  `desconto_adiantamento` decimal(15,2) NOT NULL,
  `outros_descontos` decimal(15,2) NOT NULL,
  `salario_liquido` decimal(15,2) NOT NULL,
  `data_pagamento` date DEFAULT NULL,
  `pago` tinyint(1) DEFAULT NULL,
  `transacao_id` int(11) DEFAULT NULL,
  `forma_pagamento` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `funcionario_id` (`funcionario_id`),
  KEY `transacao_id` (`transacao_id`),
  FOREIGN KEY (`funcionario_id`) REFERENCES `funcionarios` (`id`),
  FOREIGN KEY (`transacao_id`) REFERENCES `transacoes` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `folha_pagamentos`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `folha_pagamentos` WRITE;
/*!40000 ALTER TABLE `folha_pagamentos` DISABLE KEYS */;
INSERT INTO `folha_pagamentos` VALUES
(5,1,'2026-03',1800.00,135.00,100.00,0.00,1565.00,'2026-03-08',1,15,'Chave Pix'),
(6,2,'2026-03',1900.00,190.00,0.00,0.00,1710.00,'2026-03-08',1,16,'Espécie');
/*!40000 ALTER TABLE `folha_pagamentos` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `funcionario_lancamentos`
--

DROP TABLE IF EXISTS `funcionario_lancamentos`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `funcionario_lancamentos` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `funcionario_id` int(11) NOT NULL,
  `tipo` varchar(20) NOT NULL,
  `valor` decimal(15,2) NOT NULL,
  `data` date NOT NULL,
  `observacao` varchar(255) DEFAULT NULL,
  `folha_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `funcionario_id` (`funcionario_id`),
  KEY `fk_folha_id` (`folha_id`),
  FOREIGN KEY (`funcionario_id`) REFERENCES `funcionarios` (`id`),
  FOREIGN KEY (`folha_id`) REFERENCES `folha_pagamentos` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `funcionario_lancamentos`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `funcionario_lancamentos` WRITE;
/*!40000 ALTER TABLE `funcionario_lancamentos` DISABLE KEYS */;
INSERT INTO `funcionario_lancamentos` VALUES
(1,1,'Adiantamento',100.00,'2026-03-06','Vale de adiantamento',5);
/*!40000 ALTER TABLE `funcionario_lancamentos` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `funcionarios`
--

DROP TABLE IF EXISTS `funcionarios`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `funcionarios` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nome` varchar(100) NOT NULL,
  `cpf` varchar(14) DEFAULT NULL,
  `salario_bruto` decimal(15,2) NOT NULL,
  `data_admissao` date DEFAULT NULL,
  `ativo` tinyint(1) DEFAULT NULL,
  `carteira_id` int(11) DEFAULT NULL,
  `inss_percent` decimal(5,2) NOT NULL DEFAULT 7.50,
  `chave_pix` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `cpf` (`cpf`),
  KEY `carteira_id` (`carteira_id`),
  FOREIGN KEY (`carteira_id`) REFERENCES `carteiras` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `funcionarios`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `funcionarios` WRITE;
/*!40000 ALTER TABLE `funcionarios` DISABLE KEYS */;
INSERT INTO `funcionarios` VALUES
(1,'JOÃO DA SILVA','168.995.350-09',1800.00,'2025-01-01',1,10,7.50,'168.995.350-09'),
(2,'MARIA JOSÉ','529.982.247-25',1900.00,'2025-01-01',1,10,10.00,'168.995.350-09');
/*!40000 ALTER TABLE `funcionarios` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `gastos_cartao`
--

DROP TABLE IF EXISTS `gastos_cartao`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `gastos_cartao` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `fatura_mes` varchar(7) NOT NULL,
  `data` date NOT NULL,
  `descricao` varchar(255) NOT NULL,
  `valor` decimal(15,2) NOT NULL,
  `transacao_id` int(11) DEFAULT NULL,
  `categoria_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `transacao_id` (`transacao_id`),
  KEY `fk_gasto_categoria` (`categoria_id`),
  FOREIGN KEY (`transacao_id`) REFERENCES `transacoes` (`id`),
  FOREIGN KEY (`categoria_id`) REFERENCES `categorias` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `gastos_cartao`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `gastos_cartao` WRITE;
/*!40000 ALTER TABLE `gastos_cartao` DISABLE KEYS */;
/*!40000 ALTER TABLE `gastos_cartao` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `perfil_usuario`
--

DROP TABLE IF EXISTS `perfil_usuario`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `perfil_usuario` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nome` varchar(50) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `nome` (`nome`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `perfil_usuario`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `perfil_usuario` WRITE;
/*!40000 ALTER TABLE `perfil_usuario` DISABLE KEYS */;
INSERT INTO `perfil_usuario` VALUES
(1,'Admin'),
(4,'SuperAdmin'),
(2,'Usuário');
/*!40000 ALTER TABLE `perfil_usuario` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `transacoes`
--

DROP TABLE IF EXISTS `transacoes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `transacoes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `data` date NOT NULL,
  `descricao` varchar(255) NOT NULL,
  `valor` decimal(15,2) NOT NULL,
  `tipo` varchar(20) NOT NULL,
  `categoria_id` int(11) DEFAULT NULL,
  `carteira` varchar(50) DEFAULT NULL,
  `fixa` tinyint(1) DEFAULT NULL,
  `pago` tinyint(1) DEFAULT NULL,
  `valor_previsto` decimal(15,2) DEFAULT 0.00,
  `valor_pago` decimal(15,2) DEFAULT 0.00,
  `dia_vencimento` int(11) DEFAULT NULL,
  `removida` tinyint(1) DEFAULT 0,
  `carteira_id` int(11) DEFAULT NULL,
  `posicao` int(11) DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `categoria_id` (`categoria_id`),
  KEY `fk_transacoes_carteira` (`carteira_id`),
  FOREIGN KEY (`carteira_id`) REFERENCES `carteiras` (`id`),
  FOREIGN KEY (`categoria_id`) REFERENCES `categorias` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `transacoes`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `transacoes` WRITE;
/*!40000 ALTER TABLE `transacoes` DISABLE KEYS */;
INSERT INTO `transacoes` VALUES
(2,'2026-03-02','Salário',5000.00,'Receita',1,'Carteira 1',0,1,0.00,5000.00,2,0,10,0),
(3,'2026-03-06','Venda bolo',35.00,'Receita',3,'Carteira 1',0,1,0.00,35.00,6,0,10,0),
(4,'2026-03-06','Compras mercado',120.00,'Despesa',4,'Carteira 1',0,0,120.00,0.00,6,0,10,0),
(5,'2026-03-06','Gasolina carro',200.00,'Despesa',6,'Carteira 1',0,0,200.00,0.00,6,0,10,0),
(6,'2026-03-06','SALÁRIO',6000.00,'Receita',1,'Carteira 2',0,1,0.00,6000.00,6,0,11,0),
(7,'2026-03-06','Mensalidade Escola',950.00,'Despesa',14,'Carteira 2',0,0,950.00,0.00,6,0,11,0),
(8,'2026-03-07','Feira',2500.00,'Despesa',4,'Consolidada',0,0,2500.00,0.00,7,0,1,0),
(9,'2026-03-06','Feirinha ',2500.00,'Despesa',4,'Consolidada',0,0,2500.00,0.00,6,1,1,0),
(10,'2026-03-01','Diarista',0.00,'Despesa',21,'Consolidada',1,0,1000.00,0.00,1,0,1,0),
(11,'2026-03-06','Combustível ',200.00,'Despesa',6,'Consolidada',0,1,500.00,200.00,6,0,1,1),
(15,'2026-03-08','Salário – JOÃO DA SILVA',1565.00,'Despesa',21,'Carteira 1',0,1,0.00,1565.00,NULL,0,10,0),
(16,'2026-03-08','Salário – MARIA JOSÉ',1710.00,'Despesa',21,'Carteira 1',0,1,0.00,1710.00,NULL,0,10,0);
/*!40000 ALTER TABLE `transacoes` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `usuario_carteira`
--

DROP TABLE IF EXISTS `usuario_carteira`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `usuario_carteira` (
  `usuario_id` int(11) NOT NULL,
  `carteira_id` int(11) NOT NULL,
  PRIMARY KEY (`usuario_id`,`carteira_id`),
  KEY `carteira_id` (`carteira_id`),
  FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`) ON DELETE CASCADE,
  FOREIGN KEY (`carteira_id`) REFERENCES `carteiras` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `usuario_carteira`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `usuario_carteira` WRITE;
/*!40000 ALTER TABLE `usuario_carteira` DISABLE KEYS */;
INSERT INTO `usuario_carteira` VALUES
(6,10),
(8,10),
(7,11),
(9,11);
/*!40000 ALTER TABLE `usuario_carteira` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `usuarios`
--

DROP TABLE IF EXISTS `usuarios`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `usuarios` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL,
  `password` varchar(255) NOT NULL,
  `data_criacao` datetime DEFAULT current_timestamp(),
  `criado_por_id` int(11) DEFAULT NULL,
  `bloqueado` tinyint(1) DEFAULT 0,
  `perfil_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  KEY `fk_criado_por` (`criado_por_id`),
  KEY `fk_usuario_perfil` (`perfil_id`),
  FOREIGN KEY (`criado_por_id`) REFERENCES `usuarios` (`id`),
  FOREIGN KEY (`perfil_id`) REFERENCES `perfil_usuario` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `usuarios`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `usuarios` WRITE;
/*!40000 ALTER TABLE `usuarios` DISABLE KEYS */;
INSERT INTO `usuarios` VALUES
(1,'admin','pbkdf2:sha256:1000000$Aqu4BrJZoveRIeP6$e079f8993a3ee1644485e17b111e3989b054c12417b432cf33ad2d5a3bbf4621','2026-02-22 08:26:55',NULL,0,4),
(6,'user1','pbkdf2:sha256:600000$rxz7L9hktnNqHL4g$bbfe86cb20d6c537254bd66b56c8a92d0ee8d9be103a13191eb33f5ff36d704a','2026-03-06 14:25:16',1,0,1),
(7,'user2','pbkdf2:sha256:600000$GORU4Q2F6oWk992n$3c34109b8f93e4c638774e830779c75ef2efb4516e923ffe5d6c639258a471f9','2026-03-06 14:25:28',1,0,1),
(8,'user3','pbkdf2:sha256:600000$thFV6zlthPLmlNeb$f913f4ee7d5366e3e678bd49a77350a67945cb0aa8e91ccccf175bf922ec50d4','2026-03-06 14:25:47',1,0,2),
(9,'user4','pbkdf2:sha256:600000$X0P5NAFlNNntZ3gU$50c0ce9b37d1b76367a43d9387ceac8d21a25c6c29f51fc4f0ac9da1784032e3','2026-03-06 14:26:07',1,0,2);
/*!40000 ALTER TABLE `usuarios` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `vendas`
--

DROP TABLE IF EXISTS `vendas`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `vendas` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `ticker` varchar(100) NOT NULL,
  `quantidade` decimal(18,6) NOT NULL,
  `preco_venda` decimal(15,2) NOT NULL,
  `preco_medio_compra` decimal(15,2) NOT NULL,
  `lucro_realizado` decimal(15,2) NOT NULL,
  `data_venda` date NOT NULL,
  `carteira` varchar(50) DEFAULT 'Família',
  `carteira_id` int(11) DEFAULT NULL,
  `categoria_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_vendas_carteira` (`carteira_id`),
  KEY `fk_vendas_categoria_ativo` (`categoria_id`),
  FOREIGN KEY (`carteira_id`) REFERENCES `carteiras` (`id`),
  FOREIGN KEY (`categoria_id`) REFERENCES `categoria_ativos` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `vendas`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `vendas` WRITE;
/*!40000 ALTER TABLE `vendas` DISABLE KEYS */;
INSERT INTO `vendas` VALUES
(1,'VALE3',5.000000,74.00,72.00,10.00,'2026-03-06','Carteira 1',10,1),
(2,'HGLG11',5.000000,158.00,155.00,15.00,'2026-03-06','Carteira 1',10,2),
(3,'BOVA11',4.000000,176.39,174.00,9.56,'2026-03-06','Carteira 2',11,3),
(4,'PETR4',10.000000,42.55,40.25,23.00,'2026-03-06','Carteira 2',11,1);
/*!40000 ALTER TABLE `vendas` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*M!100616 SET NOTE_VERBOSITY=@OLD_NOTE_VERBOSITY */;

-- Dump completed on 2026-03-08 15:01:18
