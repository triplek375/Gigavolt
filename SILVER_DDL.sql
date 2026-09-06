# =====================================================================
# DEFINE SILVER TABLES
# =====================================================================
USE gigavolt_db;

CREATE TABLE companies (
    company_id INT AUTO_INCREMENT PRIMARY KEY,
    company_name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE countries (
    country_id INT AUTO_INCREMENT PRIMARY KEY,
    country_name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE states (
    state_id INT AUTO_INCREMENT PRIMARY KEY,
    state_name CHAR(2) NOT NULL,
    country_id INT NOT NULL,
    FOREIGN KEY (country_id) REFERENCES countries(country_id)
);

CREATE TABLE cities (
    city_id INT AUTO_INCREMENT PRIMARY KEY,
    city_name VARCHAR(50) NOT NULL,
    state_id INT NOT NULL,
    FOREIGN KEY (state_id) REFERENCES states(state_id)
);

CREATE TABLE locations (
    location_id INT AUTO_INCREMENT PRIMARY KEY,
    zip VARCHAR(20),
    city_id INT NOT NULL,
    FOREIGN KEY (city_id) REFERENCES cities(city_id)
);

CREATE TABLE customerStatus (
    status_id INT AUTO_INCREMENT PRIMARY KEY,
    status_name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE customers (
    customer_id VARCHAR(50) PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    company_id INT NOT NULL,
    phone VARCHAR(50) NOT NULL,
    email VARCHAR(50) NOT NULL,
    address VARCHAR(255) NOT NULL,
    location_id INT NOT NULL,
    created_date DATE NOT NULL,
    status_id INT NOT NULL,
    FOREIGN KEY (company_id) REFERENCES companies(company_id),
    FOREIGN KEY (location_id) REFERENCES locations(location_id),
    FOREIGN KEY (status_id) REFERENCES customerStatus(status_id)
);

CREATE TABLE equipmentModels (
    model_id INT AUTO_INCREMENT PRIMARY KEY,
    model_name VARCHAR(50) NOT NULL UNIQUE,
    capacity_kw DECIMAL(10,2),
    voltage DECIMAL(10,2)
);

CREATE TABLE equipmentStatus (
    status_id INT AUTO_INCREMENT PRIMARY KEY,
    status_name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE equipment (
    equipment_id VARCHAR(50) NOT NULL,
    customer_id VARCHAR(50) NOT NULL,
    model_id INT NOT NULL,
    serial_number VARCHAR(50) NOT NULL,
    install_date DATE,
    warranty_expiration DATE,
    status_id INT NOT NULL,
    location_notes TEXT,
    PRIMARY KEY (equipment_id, status_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (model_id) REFERENCES equipmentModels(model_id),
    FOREIGN KEY (status_id) REFERENCES equipmentStatus(status_id)
);

CREATE TABLE technicians (
    technician_id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL
);

CREATE TABLE serviceTypes (
    service_type_id INT AUTO_INCREMENT PRIMARY KEY,
    service_type_name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE dispatchStatus (
    status_id INT AUTO_INCREMENT PRIMARY KEY,
    status_name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE dispatches (
    dispatch_id VARCHAR(50) PRIMARY KEY,
    equipment_id VARCHAR(50) NOT NULL,
    dispatch_date DATE,
    technician_id INT NOT NULL,
    service_type_id INT NOT NULL,
    hours_spent DECIMAL(10,2),
    labor_cost DECIMAL(10,2),
    resolution_summary TEXT,
    status_id INT NOT NULL,
    FOREIGN KEY (equipment_id) REFERENCES equipment(equipment_id),
    FOREIGN KEY (technician_id) REFERENCES technicians(technician_id),
    FOREIGN KEY (service_type_id) REFERENCES serviceTypes(service_type_id),
    FOREIGN KEY (status_id) REFERENCES dispatchStatus(status_id)
);

CREATE TABLE partCategories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE manufacturers (
    manufacturer_id INT AUTO_INCREMENT PRIMARY KEY,
    manufacturer_name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE suppliers (
    supplier_id INT AUTO_INCREMENT PRIMARY KEY,
    supplier_name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE parts (
    part_id VARCHAR(50) PRIMARY KEY,
    part_name VARCHAR(100) NOT NULL,
    category_id INT NOT NULL,
    manufacturer_id INT NOT NULL,
    supplier_id INT NOT NULL,
    unit_cost DECIMAL(10,2),
    unit_price DECIMAL(10,2),
    stock_quantity INT,
    reorder_level INT,
    FOREIGN KEY (category_id) REFERENCES partCategories(category_id),
    FOREIGN KEY (manufacturer_id) REFERENCES manufacturers(manufacturer_id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
);

CREATE TABLE claimStatus (
    status_id INT AUTO_INCREMENT PRIMARY KEY,
    status_name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE warrantyClaims (
    claim_id VARCHAR(50) PRIMARY KEY,
    equipment_id VARCHAR(50) NOT NULL,
    dispatch_id VARCHAR(50), 
    part_id VARCHAR(50),
    claim_date DATE NOT NULL,
    claim_amount DECIMAL(10,2) NOT NULL,
    approved_amount DECIMAL(10,2),
    status_id INT NOT NULL,
    denial_reason TEXT,
    claim_notes TEXT,
    FOREIGN KEY (equipment_id) REFERENCES equipment(equipment_id),
    FOREIGN KEY (dispatch_id) REFERENCES dispatches(dispatch_id),
    FOREIGN KEY (part_id) REFERENCES parts(part_id),
    FOREIGN KEY (status_id) REFERENCES claimStatus(status_id)
);