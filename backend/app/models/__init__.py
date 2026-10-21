"""Import all models so Alembic/Base.metadata sees every table."""
from app.models.identity import Membership, Organization, Session, User  # noqa: F401
from app.models.materials import MaterialCatalog, MaterialSpec, OrganizationMaterial, UnitConversion  # noqa: F401
from app.models.crm import Customer, CustomerContact, CustomerInquiry, InquiryItem  # noqa: F401
from app.models.sales import Quotation, QuotationItem, QuotationVersion, SalesOrder, SalesOrderItem  # noqa: F401
from app.models.inventory import (InventoryMovement, Reservation, StockLot,  # noqa: F401
                                  StockTransfer, StorageLocation, Warehouse)
from app.models.market import MarketImportBatch, MarketImportStagedRow, MarketIngestionRun, MarketPriceAlertEvent, MarketPriceAlertRule, MarketSource, PriceObservation, PriceScenario, PriceSource  # noqa: F401
from app.models.procurement import (GoodsReceipt, PurchaseOrder, PurchaseOrderItem,  # noqa: F401
                                    PurchaseRequest, PurchaseRequestItem, RFQ, Supplier,
                                    SupplierQuote)
from app.models.fabrication import (BOMItem, BOMVersion, MaterialAllocation,  # noqa: F401
                                    ProductionOperation, QualityInspection, Routing,
                                    ScrapRecord, WorkOrder)
from app.models.projects import (BOQItem, ExtractionEvidence, Project,  # noqa: F401
                                 ProjectRequirement, Tender, TenderDocument)
from app.models.ops import (AIJob, Approval, AuditEvent, CostEstimate, CostLine,  # noqa: F401
                            Dispatch, DispatchItem, Invoice, Notification, Payment,
                            Shipment)
